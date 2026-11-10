"""Application assembly + startup/shutdown sequences (P-01 §4).

Startup: config -> logging -> database (+migrations) -> DB verify ->
permission engine -> event bus (+persistence) -> monitoring -> task
manager (+recovery) -> auth seeding -> ready. A critical failure marks the
lifecycle FAILED and readiness stays false — the app never reports healthy
on a broken foundation.
"""
from __future__ import annotations

from ..database.connection import check_database, make_engine, make_session_factory, run_migrations
from ..events.bus import EventBus
from ..events.events import Event, EventType
from ..events.subscribers import register_persistence
from ..monitoring.system_monitor import SystemMonitor
from ..permissions.approvals import ApprovalService
from ..permissions.engine import PermissionEngine
from ..tasks.manager import TaskManager
from .auth import AuthService
from .config import Settings
from .lifecycle import AppState, LifecycleManager
from .logging import configure_logging, get_logger


class Application:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.lifecycle = LifecycleManager()
        self._log = get_logger("core.application")
        self.engine = None
        self.session_factory = None
        self.bus: EventBus | None = None
        self.permissions: PermissionEngine | None = None
        self.approvals: ApprovalService | None = None
        self.monitor: SystemMonitor | None = None
        self.tasks: TaskManager | None = None
        self.auth: AuthService | None = None
        self.intelligence = None  # IntelligenceService (P-02), built at startup
        self.opportunities = None  # OpportunityService (P-03), built at startup
        self.agents = None  # AgentFactoryService (P-04), built at startup
        self.execution = None  # ExecutionService (P-05), built at startup
        self.business = None  # BusinessCreationService (P-06), built at startup
        self.financial = None  # FinancialService (P-07), built at startup
        self.survival = None  # SurvivalService (P-08), built at startup
        self.memory = None  # MemoryService (P-09), built at startup
        self.security = None  # SecurityService (P-10), built at startup
        self.operations = None  # OperationsService (P-12), built at startup
        self.portfolio = None  # PortfolioService (P-13), built at startup
        self.reliability = None  # ReliabilityService (P-15), built at startup
        self.economy = None  # EconomyService (P-16), built at startup
        self.growth = None  # GrowthService (P-17), built at startup
        self.experience = None  # ExperienceService (P-18), at startup
        self.integrations = None  # IntegrationService (Expansion F02), at startup
        self.voice = None  # VoiceService (Expansion F03), built at startup
        self.knowledge = None  # KnowledgeService (Expansion F06), at startup
        self._operations_loop = None
        self._reliability_loop = None
        self.execution_recovery: dict = {}
        self.recovered_task_ids: list[str] = []

    async def startup(self) -> None:
        s = self.settings
        self.lifecycle.transition(AppState.STARTING)
        configure_logging(
            level=s.log_level, log_file=s.effective_log_file,
            max_bytes=s.log_max_bytes, backup_count=s.log_backup_count,
            secret_values=tuple(v for v in (s.admin_password, s.dev_token, s.service_token) if v))
        self._log.info("starting AUTONOMUS Core OS", extra={})
        self._log.info(f"configuration loaded: {s.redacted_dict()}")
        try:
            s.data_dir.mkdir(parents=True, exist_ok=True)
            self.engine = make_engine(s.effective_database_url)
            if s.auto_migrate:
                run_migrations(s.effective_database_url)
                # Alembic's env may touch logging configuration; restore the
                # application pipeline so post-migration logs are not lost.
                configure_logging(
                    level=s.log_level, log_file=s.effective_log_file,
                    max_bytes=s.log_max_bytes, backup_count=s.log_backup_count,
                    secret_values=tuple(v for v in (s.admin_password, s.dev_token, s.service_token) if v))
            else:  # test/dev fallback: create schema directly
                from ..database.models import Base
                Base.metadata.create_all(self.engine)
            if not check_database(self.engine):
                raise RuntimeError("database connectivity check failed")
            self.session_factory = make_session_factory(self.engine)

            self.permissions = PermissionEngine(self.session_factory)
            self.approvals = ApprovalService(self.session_factory)
            self.bus = EventBus(rate_limit_per_second=s.event_rate_limit_per_second,
                                max_depth=s.event_max_depth)
            register_persistence(self.bus, self.session_factory)

            self.monitor = SystemMonitor(s, self.engine)
            self.tasks = TaskManager(
                self.session_factory, self.bus, self.permissions,
                capacity=s.queue_capacity, max_concurrency=s.max_concurrency,
                retry_base_delay=s.retry_base_delay_seconds,
                retry_max_delay=s.retry_max_delay_seconds,
                admission_guard=lambda: self.monitor.admission_block_reason() if self.monitor else None,
                monitor=self.monitor)
            self.monitor.queue_stats = self.tasks.queue
            self.auth = AuthService(self.session_factory, s)
            self.auth.seed_admin_from_settings()

            # P-02 Master Intelligence: providers + service, built on the
            # P-01 task manager / permissions / approvals / event bus.
            from ..intelligence.providers import CloudProviderStub, OllamaProvider
            from ..intelligence.service import IntelligenceService
            providers = {
                "ollama": OllamaProvider(s.ollama_base_url, s.ollama_timeout_seconds),
                "cloud": CloudProviderStub(s.cloud_ai_enabled),
            }
            self.intelligence = IntelligenceService(
                self.session_factory, self.bus, self.permissions, self.tasks,
                self.approvals, s, monitor=self.monitor, providers=providers)
            self.intelligence.seed_default_profiles()

            # P-03 Opportunity Discovery: service + seed catalogue + the
            # governed research task handler (a closure over the service,
            # because P-01 handler context carries only task_id/monitor).
            from ..opportunities.schemas import ResearchTaskPayload
            from ..opportunities.service import RESEARCH_HANDLER, OpportunityService
            self.opportunities = OpportunityService(
                self.session_factory, self.bus, self.permissions, self.tasks, s,
                recorder=self.intelligence.recorder)
            self.opportunities.seed_sources()
            self.opportunities.seed_scoring_config()
            # P-14 Stage B (DEF-E1): wire P-03 into P-02's thin
            # assessment path now that both services exist.
            self.intelligence.attach_opportunities(self.opportunities)
            # P-14 Stage B (DEF-A5): feed the monitor the cached
            # provider-probe result so provider health shows in the
            # system status outside the dashboard call path.
            self.monitor.provider_probe = (
                self.intelligence.cached_models_status)

            async def _research_handler(payload: dict, context: dict) -> dict:
                return await self.opportunities.run_research_stage(payload["session_id"])

            self.tasks.registry.register(RESEARCH_HANDLER, _research_handler, ResearchTaskPayload)

            # P-04 Dynamic Agent Factory: service over the P-01 substrate,
            # sharing the P-02 model router (bound ONCE — agents are
            # logical configurations, never per-agent model instances).
            # Seeds: factory settings, capability catalogue, starter
            # templates. P-04 deliberately registers NO new task handlers:
            # assignments execute through the existing registry.
            from ..agents.service import AgentFactoryService
            self.agents = AgentFactoryService(
                self.session_factory, self.bus, self.permissions, self.tasks,
                self.approvals, s, monitor=self.monitor,
                intelligence=self.intelligence)
            self.agents.seed_settings()
            self.agents.seed_capabilities()
            self.agents.seed_templates()

            # P-05 Universal Digital Execution Engine: service over the
            # P-01 substrate, capability validation via the P-04 factory's
            # CapabilityService (the same instance). Seeds settings,
            # tools (with truthful per-environment health), workspaces and
            # the P-05 capability-support flip; then the restart-recovery
            # scan (§16.4 — interrupted work is never blindly repeated).
            from ..execution.service import ExecutionService
            self.execution = ExecutionService(
                self.session_factory, settings=s, permissions=self.permissions,
                approvals=self.approvals, capabilities=self.agents.capabilities,
                bus=self.bus)
            self.execution.seed()
            self.execution_recovery = self.execution.recover_interrupted()
            if self.execution_recovery.get("interrupted_requests"):
                self._log.warning(
                    "execution recovery: "
                    f"{len(self.execution_recovery['interrupted_requests'])} "
                    "interrupted request(s) marked INTERRUPTED")

            # P-06 Business Creation Engine: orchestration over P-03
            # (inputs), P-04 (agents), P-05 (execution) and P-01
            # (approvals/permissions/audit). Seeds owner-governed
            # settings and the business template registry (validated
            # against the live P-05 tool registry).
            from ..business.service import BusinessCreationService
            self.business = BusinessCreationService(
                self.session_factory, settings=s,
                permissions=self.permissions, approvals=self.approvals,
                bus=self.bus, opportunities=self.opportunities,
                agents=self.agents, execution=self.execution)
            self.business.seed_settings()
            self.business.seed_templates()

            # P-07 Financial Intelligence Engine: deterministic
            # accounting/verification/governance over the P-01
            # substrate (approvals, audit, system_config) and the
            # P-06 business registry + financial-inputs bridge. Seeds
            # owner-governed settings, the currency registry and the
            # provider registry (fake active; Stripe interface-only).
            # No transaction-execution capability exists in P-07.
            from ..financial.service import FinancialService
            self.financial = FinancialService(
                self.session_factory, settings=s,
                permissions=self.permissions, approvals=self.approvals,
                bus=self.bus, business=self.business)
            self.financial.seed_settings()
            self.financial.payments.seed_providers()

            # P-08 Survival and Scaling Engine: health, decisions,
            # experiments, scaling, recovery/closure, portfolio and
            # forecasting over P-06 (businesses/lifecycle) and P-07
            # (the ONLY financial source). Seeds owner-governed
            # survival settings. No financial calculation exists in
            # P-08; Level 4 actions have no agent path.
            from ..survival.service import SurvivalService
            self.survival = SurvivalService(
                self.session_factory, bus=self.bus,
                approvals=self.approvals,
                recorder=self.intelligence.recorder,
                business=self.business, financial=self.financial,
                agents=self.agents, execution=self.execution,
                tasks=self.tasks)

            # P-09 Memory and Continuous Learning Engine: classified,
            # provenance-carrying memory over P-01..P-08 (P-07 by
            # reference only), deterministic ingestion/retrieval/
            # learning, the completed P-04 agent-memory interface and
            # the memory_write capability flip. Memory is data, never
            # authority: the service holds no governance write path.
            from ..memory.service import MemoryService
            self.memory = MemoryService(
                self.session_factory, bus=self.bus, agents=self.agents)
            self.memory.seed_settings()
            self.memory.seed_capability_flip()
            self.memory.wire_agent_memory()
            # P-14 Stage B (DEF-E2): wire P-09 retrieval into P-02
            # mission context building now that both services exist.
            self.intelligence.attach_memory(self.memory)
            # P-14 Stage B (DEF-I6): wire P-09 outcome ingestion into
            # the completion points of P-05, P-06 and P-07 now that
            # P-09 exists. Ingestion is best-effort at every site.
            _ingest = self.memory.ingestion.ingest
            self.execution.outcome_ingestor = _ingest
            self.business.outcome_ingestor = _ingest
            self.financial.outcome_ingestor = _ingest

            # P-10 Security and Governance Engine: a layer over the
            # P-01 substrate (engine, approvals, audit, sessions,
            # config), P-05 (path validator, credential broker,
            # browser sessions) and P-07 (financial settings,
            # read-only). Seeds owner-governed security settings +
            # the threat register, and wires the login-throttling
            # guard into P-01 auth. Creates no parallel auth,
            # permission, approval, audit or ledger system.
            from ..security.service import SecurityService
            self.security = SecurityService(
                self.session_factory, permissions=self.permissions,
                approvals=self.approvals, app_settings=s,
                financial=self.financial, bus=self.bus)
            self.security.seed_settings()
            self.security.seed_threat_register()
            self.auth.login_guard = self.security.login_guard
            # Expansion Feature 1 (Identity & Device Security):
            # wire the device hook into P-01 auth, following the
            # login_guard late-attachment pattern — password logins
            # may then bind sessions to trusted registered devices,
            # and bound sessions are refused at resolution while
            # their device is not trusted.
            self.auth.device_hook = self.security.devices
            # P-14 Stage B (DEF-I5): route P-05 execution submission
            # through the P-10 PermissionBroker now that P-10 exists
            # (P-05 is assembled before P-10, so the handle is
            # late-attached, like the DEF-E1/E2/I6 handles above).
            self.execution.permission_broker = self.security.broker

            # P-12 Autonomous Operations Engine: a coordination layer
            # over everything above. It composes the P-10 broker for
            # authorization, P-01 approvals, P-07 budgets, the P-01
            # task queue and P-05 execution; it owns only workflow
            # coordination state (no ledger, no approval store, no
            # second scheduler — its trigger loop feeds the existing
            # substrates). Interrupted workflows are parked in
            # RECOVERY_PENDING at startup, never blindly re-run.
            from ..operations.service import OperationsService
            self.operations = OperationsService(
                self.session_factory, settings=s, bus=self.bus,
                approvals=self.approvals, tasks=self.tasks,
                agents=self.agents, execution=self.execution,
                business=self.business, financial=self.financial,
                survival=self.survival, memory=self.memory,
                security=self.security, monitor=self.monitor)
            self.recovered_workflow_count = \
                self.operations.recover_interrupted()
            if s.environment != "test":
                import asyncio as _asyncio
                self._operations_loop = _asyncio.create_task(
                    self.operations.start_loop())

            # P-13 Multi-business Coordination Engine: a
            # coordination/intelligence layer over P-01–P-12. It
            # owns only portfolio state (membership, relationships,
            # opportunities, shared services, resources, grants,
            # coordination workflows, reports, venture proposals).
            # P-06 keeps business identity/lifecycle, P-07 keeps all
            # money (portfolio finance is analytical; internal
            # allocations never enter the ledger; P-13 never
            # transfers funds), P-12 executes portfolio workflows,
            # P-09 memory crosses businesses only when explicitly
            # ORGANIZATION_SHARED.
            from ..portfolio.service import PortfolioService
            self.portfolio = PortfolioService(
                self.session_factory, bus=self.bus,
                business=self.business, financial=self.financial,
                survival=self.survival, operations=self.operations,
                memory=self.memory, agents=self.agents,
                discovery=self.opportunities)
            self.portfolio.seed_settings()

            # P-15 Performance, Reliability & Production Readiness:
            # an observation layer over everything above. It owns no
            # queue, scheduler, breaker, backup or ledger — it samples
            # the P-01 monitor, evaluates reliability conditions into
            # its incident register, computes the §13 readiness score
            # from live evidence and delegates every control to the
            # owning engine. Its sampler loop (the §11.5 long-duration
            # harness) runs beside the P-12 loop outside tests.
            from ..reliability.service import ReliabilityService
            self.reliability = ReliabilityService(self)
            self.reliability.seed_settings()
            if s.environment != "test":
                import asyncio as _asyncio2
                self._reliability_loop = _asyncio2.create_task(
                    self.reliability.run_sampler())

            # P-16 AI Economy Expansion Engine: an intelligence and
            # recommendation layer over P-01–P-15. It owns only
            # economy state (market records, the opportunity
            # pipeline, strategies, classifications,
            # commercialization, allocation/reinvestment
            # recommendations, experiment proposals, decision
            # records, risk snapshots). P-07 remains the only
            # financial authority (P-16 reads it live and executes
            # nothing), P-06 creates businesses, P-08 runs
            # experiments, P-01 holds approvals. The owner's
            # profitability gate is enforced inside the service.
            from ..economy.service import EconomyService
            self.economy = EconomyService(self)
            self.economy.seed_settings()

            # P-17 Customer Acquisition, Marketing & Revenue Growth
            # Engine: growth intelligence and execution support over
            # P-01–P-16. It owns only growth state (personas, ICPs,
            # channel evaluations, strategies, campaigns, content,
            # leads, the sales pipeline, the CRM layer, funnels,
            # SEO records, communication queues, partnerships,
            # growth experiments). P-07 remains the only financial
            # authority (P-17 reads it live; spend exists only as
            # P-07 records prepared through P-07's approval path),
            # P-08 runs experiments (P-17 hands approved designs
            # over), P-06 owns lifecycle, P-13 owns portfolio
            # coordination, and P-16's profitability gate is
            # consumed live, never rebuilt.
            from ..growth.service import GrowthService
            self.growth = GrowthService(self)
            self.growth.seed_settings()
            self.growth.seed_agent_templates()

            # P-18: the Customer Experience, Service Delivery &
            # Customer Success Engine — a coordinating layer over
            # P-01–P-17. It owns only experience state (lifecycle
            # templates, onboarding, fulfilment tracking, SLA
            # policies, support tickets, the knowledge base,
            # grounded support answers, queued communications,
            # feedback, health snapshots, incidents, resolution
            # recommendations, quality reviews, success tasks).
            # P-17's crm_customers remain the only customer store
            # (P-18 references them, never copies them), P-07
            # remains the only financial authority (refunds and
            # goodwill execute only as P-07 records through its
            # approval path; P-18 holds no money columns), P-12
            # owns escalations and scheduled follow-ups, P-09 owns
            # memory (resolution patterns are fed through its
            # ingestion), and P-16's profitability gate is never
            # touched. No support channel is connected:
            # communications queue and are honestly blocked at
            # dispatch.
            from ..experience.service import ExperienceService
            self.experience = ExperienceService(self)
            self.experience.seed_settings()
            self.experience.seed_agent_templates()

            # Expansion Feature 2 — Universal Integration Framework:
            # the connector registry + capability contract +
            # governed invocation layer over P-10 (credentials and
            # authorization) and P-01 (permissions, audit). It owns
            # only framework state (registry rows, the invocation
            # ledger); it stores no secret value (P-10's registry
            # holds names; values resolve through P-10's brokered
            # use at invocation time), moves no money (P-07), and
            # claims no provider supported without an implemented,
            # tested adapter. Seeds the built-in catalogue: the
            # local reference connector plus the P-07/P-17/P-18
            # surfaces registered honestly as
            # requires_owner_configuration (no adapters).
            from ..integrations.service import IntegrationService
            self.integrations = IntegrationService(self)
            self.integrations.seed_connectors()

            # Expansion Feature 3 — Voice Assistant: an INPUT
            # CHANNEL into the governed machinery, never an
            # authority. It consumes P-02 (missions/plans/execution),
            # P-09 (best-effort verified-outcome feed only), P-10
            # (broker intake decisions) and P-01 (principals, audit).
            # It owns only voice records (sessions, audio metadata,
            # transcripts with provenance, interpreted commands);
            # audio bytes live under the data dir. No speech
            # provider is configured by default: the one real local
            # candidate (faster-whisper) honestly reports itself
            # unavailable until the owner installs it and a model
            # (DEF-A2 — real-model acceptance belongs to the
            # owner's machine). No test double is ever attached at
            # startup.
            from ..voice.service import VoiceService
            self.voice = VoiceService(self)

            # Expansion Feature 6 — Personal Knowledge & File
            # Intelligence: the owner's document library, built
            # ON P-09 — chunks are ingested through P-09's own
            # governed ingestion, search is P-09's retrieval with
            # citations attached, deletion is P-09's governed
            # deletion. It owns only the catalogue (collections,
            # document provenance, chunk locators); it keeps no
            # index, no memory store and no money surface.
            # Features 4–5 are DEFERRED by owner decision (they
            # need his Windows machine); F06 was approved to
            # proceed ahead of them.
            from ..knowledge.service import KnowledgeService
            self.knowledge = KnowledgeService(self)

            self.recovered_task_ids = self.tasks.recover_interrupted()
            if self.recovered_task_ids:
                self._log.warning(f"recovered {len(self.recovered_task_ids)} interrupted task(s); "
                                  "they are PAUSED pending operator review")
            await self.tasks.start()
        except Exception:
            self.lifecycle.transition(AppState.FAILED)
            self._log.exception("startup failed; application marked FAILED")
            raise

        violations = self.monitor.threshold_violations()
        if violations:
            self.lifecycle.transition(AppState.DEGRADED,
                                      reason=f"resource thresholds exceeded at startup: {violations}")
        else:
            self.lifecycle.transition(AppState.READY)
        await self.bus.publish(Event(EventType.APPLICATION_STARTED, source="core.application"))
        await self.bus.publish(Event(EventType.APPLICATION_READY, source="core.application",
                                     payload={"state": self.lifecycle.state.value}))
        self._log.info(f"application ready (state={self.lifecycle.state.value})")

    async def shutdown(self) -> None:
        if self.lifecycle.state in (AppState.STOPPED, AppState.FAILED):
            return
        self.lifecycle.transition(AppState.STOPPING)
        self._log.info("graceful shutdown initiated")
        if self.bus:
            await self.bus.publish(Event(EventType.APPLICATION_STOPPING, source="core.application"))
        if self.operations is not None:
            await self.operations.stop_loop()
            if self._operations_loop is not None:
                self._operations_loop.cancel()
        if self.reliability is not None:
            await self.reliability.stop_sampler()
            if self._reliability_loop is not None:
                self._reliability_loop.cancel()
        if self.intelligence is not None:
            await self.intelligence.close()
        if self.tasks:
            await self.tasks.stop(timeout=self.settings.shutdown_timeout_seconds)
        if self.bus:
            await self.bus.publish(Event(EventType.APPLICATION_STOPPED, source="core.application"))
        if self.engine:
            self.engine.dispose()
        self.lifecycle.transition(AppState.STOPPED)
        self._log.info("application stopped")
