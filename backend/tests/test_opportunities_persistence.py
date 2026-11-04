"""P-03 §21 persistence tests.

These prove the twelve P-03 tables are actually written and read, not merely
created by a migration.  Three properties matter more than the rest and get their
own tests:

* **Money survives exactly.**  SQLite has no decimal type, so a Numeric column
  degrades to REAL.  The §13 margin and break-even arithmetic is deterministic and
  hand-verified; persisting it through a float would silently change the numbers
  between a write and a read.  Every monetary column is therefore exact decimal
  text, and ``0.1`` is asserted to come back as ``0.1``.
* **An empty result is still a result.**  A risk assessment with zero findings
  means "nothing was blocked", not "nothing was learned".  If only the child rows
  were stored, that verdict would vanish.
* **Refusals are kept.**  An absence of evidence is only interpretable when the
  reason for the absence is recorded alongside it.

Async work is driven with ``asyncio.run`` because the project has no
pytest-asyncio (decision D-14 / requirements pin), matching the existing P-02
persistence tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from app.database.connection import Database
from app.opportunities.repository import (
    MAPPING_GAPS,
    OpportunityRepository,
    verify_mapping_completeness,
)
from app.opportunities.schemas import (
    Assumption,
    BudgetBand,
    BudgetConstraint,
    BusinessModelAnalysis,
    BusinessModelType,
    CommercialAssessment,
    CompetitorAssessment,
    CompetitorProfile,
    CostItem,
    CostStructure,
    DistributionChannel,
    EvidenceClassification,
    EvidenceReliability,
    EvidenceType,
    MarketAssessment,
    Opportunity,
    OpportunityCandidate,
    OpportunityState,
    Provenance,
    RiskAssessment,
    RiskFinding,
    RiskSeverity,
    SourceDescriptor,
    SourceEvidence,
    SourceStatus,
    SourceType,
    AcquisitionMethod,
    TrustDomain,
    ValidationLevel,
)

P02_HEAD = "2a904ceb99c4"
#: The P-03 revision that creates the twelve tables. Read from the filesystem
#: rather than retyped, so renaming a revision cannot silently stale this test.
P03_TABLES_REVISION = next(
    Path(__file__).resolve().parents[1]
    .joinpath("app/database/migrations/versions")
    .glob("*_p_03_opportunity_discovery_schema.py")
).name.split("_")[0]
#: The last P-03 revision. This test measures the P-03 delta, so it must stop
#: there: "head" moves on with every later phase, and pinning it keeps the
#: assertion about P-03 rather than about whatever the newest revision happens
#: to add. Derived from the filename, like P03_TABLES_REVISION above.
P03_HEAD = next(
    Path(__file__).resolve().parents[1]
    .joinpath("app/database/migrations/versions")
    .glob("*_p_03_assessment_summaries*.py")
).name.split("_")[0]
P03_TABLES = frozenset(
    {
        "commercial_analyses",
        "competitor_records",
        "market_analyses",
        "opportunities",
        "opportunity_candidates",
        "opportunity_history",
        "opportunity_reports",
        "opportunity_scores",
        "research_sources",
        "research_sweeps",
        "risk_findings",
        "source_evidence",
    }
)


@pytest.fixture()
def migrated(settings):
    """Create the schema for tests that do not boot the application."""
    from app.database.connection import run_migrations_sync

    run_migrations_sync(settings)
    return settings


def _db_path(settings) -> Path:
    return Path(settings.database_path)


def _tables(settings) -> list[str]:
    con = sqlite3.connect(_db_path(settings))
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return sorted(r[0] for r in rows)
    finally:
        con.close()


def _schema_hash(settings) -> str:
    con = sqlite3.connect(_db_path(settings))
    try:
        rows = con.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return hashlib.sha256(json.dumps([[n, s] for n, s in rows]).encode()).hexdigest()
    finally:
        con.close()


def _columns(settings, table: str) -> list[str]:
    con = sqlite3.connect(_db_path(settings))
    try:
        return [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
    finally:
        con.close()


def _rows(settings, table: str, where: str = "", params: tuple = ()) -> list[dict]:
    con = sqlite3.connect(_db_path(settings))
    con.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in con.execute(f"SELECT * FROM {table} {where}", params)]
    finally:
        con.close()


def _alembic_cfg(settings):
    from alembic.config import Config

    # This test drives Alembic directly rather than through run_migrations_sync,
    # so it must create the directory that helper would otherwise have made.
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    backend = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "app/database/migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.sync_database_url)
    return cfg


def _candidate(**over) -> OpportunityCandidate:
    base = dict(
        candidate_id="cand-0001",
        title="Digital planner templates",
        description="sell printable planner templates",
        category="digital_product",
        discovery_method="demand_driven",
        problem_addressed="people want printable planners",
        proposed_offering="a template pack",
        budget_band=BudgetBand.TEN_TO_50,
    )
    base.update(over)
    return OpportunityCandidate(**base)


def _opportunity(**over) -> Opportunity:
    base = dict(
        opportunity_id="opp-0001",
        candidate=_candidate(),
        state=OpportunityState.RESEARCHING,
        budget=BudgetConstraint(available_capital=Decimal("0.1")),
        costs=CostStructure(),
        evidence_ids=("ev-1", "ev-2"),
        assumptions=(
            Assumption(
                statement="units are an estimate",
                basis=Provenance.ESTIMATE,
                affects=("revenue",),
                sensitivity="high",
                owner_confirmed=False,
            ),
        ),
    )
    base.update(over)
    return Opportunity(**base)


# --------------------------------------------------------------------------- #
# The migration itself
# --------------------------------------------------------------------------- #


def test_p03_migration_is_additive_and_reversible(settings):
    """Upgrade, downgrade and re-upgrade must reproduce a byte-identical schema."""
    from alembic import command

    cfg = _alembic_cfg(settings)
    command.upgrade(cfg, P02_HEAD)
    before_tables, before_hash = _tables(settings), _schema_hash(settings)

    command.upgrade(cfg, P03_HEAD)
    after_tables = _tables(settings)
    created = set(after_tables) - set(before_tables)
    assert created == P03_TABLES, f"unexpected table delta: {created ^ P03_TABLES}"
    # Nothing belonging to P-01 or P-02 may disappear.
    assert set(before_tables) <= set(after_tables)
    p03_hash = _schema_hash(settings)

    command.downgrade(cfg, P02_HEAD)
    assert _tables(settings) == before_tables
    assert _schema_hash(settings) == before_hash, "downgrade did not restore the P-02 schema"

    command.upgrade(cfg, P03_HEAD)
    assert _schema_hash(settings) == p03_hash, "re-upgrade produced a different schema"


def test_migration_is_safe_on_a_populated_database(settings):
    """A NOT NULL column with no server default breaks any database holding rows.

    Autogenerate emits the model's Python-side ``default=dict``, which never
    reaches the DDL, so SQLite refuses the statement outright:

        OperationalError: Cannot add a NOT NULL column with default value NULL

    An upgrade/downgrade round trip over an EMPTY database passes regardless -
    there is no row for the constraint to bite - which is why this test puts a real
    opportunity row in place first.  That is the state any deployment upgrading to
    this revision would actually be in.
    """
    from alembic import command

    cfg = _alembic_cfg(settings)
    command.upgrade(cfg, P03_TABLES_REVISION)
    con = sqlite3.connect(_db_path(settings))
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute(
            "INSERT INTO opportunities (id, opportunity_id, candidate_id, title, category,"
            " discovery_method, state, recommendable, budget_owner_stated, validation_level,"
            " evidence_ids, rejection_reasons, assumptions, business_model, distribution,"
            " created_at, updated_at) VALUES ('x','opp-existing','c','t','digital_product',"
            "'demand_driven','discovered',0,1,0,'[]','[]','[]','{}','[]',"
            "'2026-01-01','2026-01-01')"
        )
        con.commit()
        assert con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 1
    finally:
        con.close()

    command.upgrade(cfg, "head")  # must not raise

    con = sqlite3.connect(_db_path(settings))
    try:
        row = con.execute(
            "SELECT opportunity_id, competitor_assessment, risk_assessment FROM opportunities"
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "opp-existing", "the pre-existing row was lost by the upgrade"
    # Existing rows must be backfilled with a valid empty summary, not NULL.
    assert json.loads(row[1]) == {}
    assert json.loads(row[2]) == {}

    command.downgrade(cfg, P03_TABLES_REVISION)
    con = sqlite3.connect(_db_path(settings))
    try:
        assert con.execute("SELECT COUNT(*) FROM opportunities").fetchone()[0] == 1
        cols = [r[1] for r in con.execute("PRAGMA table_info(opportunities)")]
    finally:
        con.close()
    assert "competitor_assessment" not in cols
    assert "risk_assessment" not in cols


def test_foreign_keys_are_enforceable(migrated):
    con = sqlite3.connect(_db_path(migrated))
    con.execute("PRAGMA foreign_keys=ON")
    try:
        targets = []
        for table in sorted(P03_TABLES):
            for row in con.execute(f"PRAGMA foreign_key_list({table})"):
                # row[2] is the referenced table; row[3] is the local column.
                targets.append((table, row[3], row[2]))
        assert targets, "no foreign keys declared from the P-03 tables"
        existing = set(_tables(migrated))
        for table, column, ref in targets:
            assert ref in existing, f"{table}.{column} points at missing table {ref}"
        with pytest.raises(sqlite3.IntegrityError):
            con.execute(
                "INSERT INTO opportunities (id, opportunity_id, candidate_id, title, category,"
                " discovery_method, state, principal_id, created_at, updated_at, recommendable,"
                " budget_owner_stated, validation_level, evidence_ids, rejection_reasons,"
                " assumptions, business_model, distribution, competitor_assessment,"
                " risk_assessment) VALUES ('x','o','c','t','digital_product','demand_driven',"
                "'discovered','no-such-principal','2026-01-01','2026-01-01',0,1,0,'[]','[]',"
                "'[]','{}','[]','{}','{}')"
            )
    finally:
        con.close()


def test_no_credential_columns_exist(migrated):
    """§27: a source records that auth is required, never the secret itself."""
    forbidden = {"api_key", "apikey", "token", "secret", "password", "credential", "bearer"}
    for table in sorted(P03_TABLES):
        leaked = forbidden & {c.lower() for c in _columns(migrated, table)}
        assert not leaked, f"{table} has credential column(s): {sorted(leaked)}"


# --------------------------------------------------------------------------- #
# The mapping is not silently lossy
# --------------------------------------------------------------------------- #


def test_mapping_completeness_is_clean():
    """A pydantic field with no column makes persistence silently lossy."""
    assert MAPPING_GAPS["clean"], MAPPING_GAPS["gaps"]
    checked = verify_mapping_completeness()
    assert "Opportunity" in checked["checked"]
    assert "SourceEvidence" in checked["checked"]


# --------------------------------------------------------------------------- #
# Round trips
# --------------------------------------------------------------------------- #


def test_opportunity_round_trips_with_exact_decimals(migrated):
    async def go():
        repo = OpportunityRepository(Database(migrated))
        await repo.save_opportunity(_opportunity())
        loaded = await repo.load_opportunity("opp-0001")
        await repo.save_opportunity(_opportunity())  # keep the handle alive
        return repo, loaded

    repo, loaded = asyncio.run(go())
    assert loaded is not None
    assert loaded.opportunity_id == "opp-0001"
    assert loaded.state is OpportunityState.RESEARCHING
    assert loaded.candidate.category.value == "digital_product"
    assert loaded.candidate.budget_band is BudgetBand.TEN_TO_50
    # generated_by is a Literal, not an enum.
    assert loaded.candidate.generated_by == "deterministic_rule"
    assert loaded.evidence_ids == ("ev-1", "ev-2")

    # THE CRITICAL ASSERTION: 0.1 must come back as exactly 0.1.
    assert loaded.budget.available_capital == Decimal("0.1")
    assert str(loaded.budget.available_capital) == "0.1"

    # Assumptions are models, not dicts, and their enum survives the text form.
    assert isinstance(loaded.assumptions[0], Assumption)
    assert loaded.assumptions[0].basis is Provenance.ESTIMATE
    assert loaded.assumptions[0].affects == ("revenue",)
    assert loaded.assumptions[0].sensitivity == "high"

    # Required fields must be supplied on read even when nothing was analysed yet.
    assert isinstance(loaded.costs, CostStructure)
    assert loaded.validation.level is ValidationLevel.LEVEL_0_IDEA


def test_unknown_opportunity_returns_none(migrated):
    async def go():
        return await OpportunityRepository(Database(migrated)).load_opportunity("nope")

    assert asyncio.run(go()) is None


def test_save_is_an_upsert_not_an_insert(migrated):
    async def go():
        repo = OpportunityRepository(Database(migrated))
        await repo.save_opportunity(_opportunity())
        await repo.save_opportunity(_opportunity(state=OpportunityState.EVIDENCE_REVIEW))
        return repo, await repo.load_opportunity("opp-0001"), await repo.count_opportunities()

    repo, loaded, count = asyncio.run(go())
    assert loaded.state is OpportunityState.EVIDENCE_REVIEW
    assert count == 1, "upsert duplicated the row"


def test_business_model_and_distribution_round_trip(migrated):
    async def go():
        repo = OpportunityRepository(Database(migrated))
        await repo.save_opportunity(_opportunity())
        bm = BusinessModelAnalysis(
            model_type=BusinessModelType.ONE_TIME_SALE,
            revenue_mechanism="one-time template sales",
            price_point=Decimal("19.00"),
            price_provenance=Provenance.QUOTED,
        )
        dc = DistributionChannel(channel="organic search", kind="organic_search")
        first = await repo.load_opportunity("opp-0001")
        await repo.save_opportunity(first.model_copy(update={"business_model": bm, "distribution": (dc,)}))
        return await repo.load_opportunity("opp-0001")

    loaded = asyncio.run(go())
    assert isinstance(loaded.business_model, BusinessModelAnalysis)
    assert loaded.business_model.model_type is BusinessModelType.ONE_TIME_SALE
    assert loaded.business_model.price_point == Decimal("19.00")
    assert loaded.business_model.price_provenance is Provenance.QUOTED
    assert len(loaded.distribution) == 1
    assert isinstance(loaded.distribution[0], DistributionChannel)
    assert loaded.distribution[0].channel == "organic search"


def test_evidence_round_trips(migrated):
    async def go():
        repo = OpportunityRepository(Database(migrated))
        ev = SourceEvidence(
            evidence_id="ev-1",
            opportunity_id="opp-0001",
            evidence_type=EvidenceType.COMPETITOR_PRICING,
            classification=EvidenceClassification.SUPPORTING,
            claim="TEST FIXTURE planner at 19.99",
            numeric_value=Decimal("19.99"),
            unit="USD",
            source_id="mock-1",
            reliability=EvidenceReliability.PLAUSIBLE,
            independence_group="pricing:usd",
            stale_after_days=90,
        )
        await repo.save_evidence(ev)
        return (await repo.list_evidence(opportunity_id="opp-0001"))[0]

    back = asyncio.run(go())
    assert back.numeric_value == Decimal("19.99")
    assert back.classification is EvidenceClassification.SUPPORTING
    assert back.reliability is EvidenceReliability.PLAUSIBLE
    assert back.trust_domain is TrustDomain.EXTERNAL
    assert back.independence_group == "pricing:usd"
    assert back.stale_after_days == 90


def test_source_descriptor_round_trips_without_secrets(migrated):
    async def go():
        repo = OpportunityRepository(Database(migrated))
        desc = SourceDescriptor(
            source_id="mkt-1",
            name="A marketplace",
            source_type=SourceType.MARKETPLACE,
            access_method=AcquisitionMethod.HTTP_GET,
            requires_auth=True,
            auth_mechanism="api_key",
            licensing="research use only",
            reliability=EvidenceReliability.UNTRUSTED,
            supported_operations=("search", "listing"),
            status=SourceStatus.AUTHORIZED,
            endpoint_template="https://mkt.example/s?q={query}",
        )
        await repo.save_source(desc)
        return await repo.list_sources()

    sources = asyncio.run(go())
    assert len(sources) == 1
    assert sources[0].source_id == "mkt-1"
    assert sources[0].auth_mechanism == "api_key"
    assert sources[0].refresh_frequency == "manual"
    assert sources[0].supported_operations == ("search", "listing")


def test_refusals_are_persisted(migrated):
    """An absence of evidence must carry the reason for the absence."""

    async def go():
        repo = OpportunityRepository(Database(migrated))
        await repo.record_sweep(
            opportunity_id="opp-0001",
            stage="acquisition",
            source_ids=("mkt-1", "search-1"),
            responses_obtained=0,
            evidence_extracted=0,
            refusals=[
                {"source_id": "mkt-1", "category": "host_not_permitted", "detail": "not allowlisted"},
                {"source_id": "search-1", "category": "host_not_permitted", "detail": "not allowlisted"},
            ],
        )
        return await repo.list_sweeps("opp-0001")

    sweeps = asyncio.run(go())
    assert len(sweeps) == 1
    assert len(sweeps[0]["refusals"]) == 2
    assert sweeps[0]["responses_obtained"] == 0, "a zero response count must not be guessed upwards"
    assert {r["category"] for r in sweeps[0]["refusals"]} == {"host_not_permitted"}


def test_history_is_append_only_and_ordered(migrated):
    async def go():
        repo = OpportunityRepository(Database(migrated))
        await repo.append_history(
            opportunity_id="opp-0001", from_state="discovered", to_state="researching",
            reason="research started",
        )
        await repo.append_history(
            opportunity_id="opp-0001", from_state="researching", to_state="evidence_review",
            reason="evidence collected",
        )
        return await repo.list_history("opp-0001")

    history = asyncio.run(go())
    assert [h["to_state"] for h in history] == ["researching", "evidence_review"]
    assert all(h["actor"] == "system" for h in history)
    assert all(h["reason"] for h in history), "a transition without a reason is not auditable"


def test_analysis_records_round_trip(migrated):
    async def go():
        repo = OpportunityRepository(Database(migrated))
        await repo.save_opportunity(_opportunity())
        await repo.save_market_analysis(
            "opp-0001",
            MarketAssessment(
                verdict="demand_plausible",
                demand_evidence_level=EvidenceClassification.SUPPORTING,
                problem_importance="moderate",
                problem_importance_basis="TEST FIXTURE 3 weak problem signals observed",
                data_gaps=("no search volume available",),
                reasons=("2 supporting signals",),
            ),
        )
        asm = Assumption(statement="units are an estimate", basis=Provenance.ESTIMATE)
        await repo.save_commercial_analysis(
            "opp-0001",
            CommercialAssessment(
                verdict="unaffordable",
                viable=False,
                affordable=False,
                costs=CostStructure(
                    items=(
                        CostItem(
                            name="inventory", amount=Decimal("800.00"),
                            provenance=Provenance.QUOTED, kind="startup",
                            billing_period="once", evidence_id="ev-c",
                        ),
                    )
                ),
                unpriced_cost_items=(),
                budget_was_modified=False,
                assumptions=(asm,),
                reasons=("the conservative scenario exceeds the available capital",),
            ),
        )
        await repo.save_competitor_assessment(
            "opp-0001",
            CompetitorAssessment(
                market_saturation="sparse",
                verdict="crowded_but_viable",
                gaps_identified=("no offline mode",),
                price_range_low=Decimal("19.00"),
                price_range_high=Decimal("29.00"),
                competitors=(
                    CompetitorProfile(
                        competitor_id="cmp-1",
                        name="TEST FIXTURE Acme",
                        price_points=(Decimal("19.00"), Decimal("29.00")),
                        pricing_provenance=Provenance.QUOTED,
                        review_count=42,
                        # A rating or review count must state where it came from;
                        # CompetitorProfile refuses one that does not.
                        rating_provenance=Provenance.ESTIMATE,
                        identified_gaps=("no offline mode",),
                        evidence_ids=("ev-1",),
                        inspected=False,
                    ),
                ),
            ),
        )
        await repo.save_risk_assessment(
            "opp-0001",
            RiskAssessment(
                verdict="acceptable",
                findings=(
                    RiskFinding(
                        finding_id="rk-1",
                        category="platform_policy",
                        severity=RiskSeverity.LOW,
                        description="no platform was named, so no restrictions were checked",
                    ),
                ),
            ),
        )
        return repo

    asyncio.run(go())
    market = _rows(migrated, "market_analyses", "WHERE opportunity_id=?", ("opp-0001",))
    assert market and market[0]["verdict"] == "demand_plausible"
    assert market[0]["demand_evidence_level"] == "supporting"

    commercial = _rows(migrated, "commercial_analyses", "WHERE opportunity_id=?", ("opp-0001",))
    assert commercial and commercial[0]["verdict"] == "unaffordable"
    assert '"800.00"' in commercial[0]["costs"], "money must be stored as exact decimal text"
    assert commercial[0]["budget_was_modified"] in (0, False)
    assert '"statement"' in commercial[0]["assumptions"], "assumptions must serialise to JSON"

    competitors = _rows(migrated, "competitor_records", "WHERE opportunity_id=?", ("opp-0001",))
    assert competitors and competitors[0]["name"] == "TEST FIXTURE Acme"
    assert json.loads(competitors[0]["price_points"]) == ["19.00", "29.00"]
    # A competitor merely named is not a competitor inspected.
    assert competitors[0]["inspected"] in (0, False)

    risks = _rows(migrated, "risk_findings", "WHERE opportunity_id=?", ("opp-0001",))
    assert risks and risks[0]["finding_id"] == "rk-1"
    assert risks[0]["category"] == "platform_policy"


def test_assessment_summaries_survive_zero_children(migrated):
    """An empty finding list is a result, not an absence of one."""

    async def go():
        repo = OpportunityRepository(Database(migrated))
        await repo.save_opportunity(_opportunity())
        await repo.save_risk_assessment(
            "opp-0001", RiskAssessment(verdict="acceptable", findings=(), blocked=False)
        )
        await repo.save_competitor_assessment(
            "opp-0001",
            CompetitorAssessment(
                competitors=(), market_saturation="unknown", verdict="insufficient_data"
            ),
        )
        return repo

    asyncio.run(go())
    assert _rows(migrated, "risk_findings", "WHERE opportunity_id=?", ("opp-0001",)) == []
    assert _rows(migrated, "competitor_records", "WHERE opportunity_id=?", ("opp-0001",)) == []

    opp = _rows(migrated, "opportunities", "WHERE opportunity_id=?", ("opp-0001",))[0]
    risk_summary = json.loads(opp["risk_assessment"])
    assert risk_summary["verdict"] == "acceptable"
    assert risk_summary["blocked"] is False
    comp_summary = json.loads(opp["competitor_assessment"])
    assert comp_summary["market_saturation"] == "unknown"
    assert comp_summary["verdict"] == "insufficient_data"


def test_summary_for_unknown_opportunity_is_refused(migrated):
    """Storing a summary against an opportunity that does not exist must fail loudly."""

    async def go():
        repo = OpportunityRepository(Database(migrated))
        await repo.save_risk_assessment("does-not-exist", RiskAssessment(verdict="acceptable"))

    with pytest.raises(ValueError, match="unknown opportunity"):
        asyncio.run(go())
