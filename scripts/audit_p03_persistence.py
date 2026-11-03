#!/usr/bin/env python3
"""Audit the P-03 persistence mapping against the real schemas.

Two failure modes make persistence silently wrong, and neither shows up until data
has already been lost:

1. **An invented attribute.**  ``opportunity.recommendable`` reads as plausible
   English and raises ``AttributeError`` only at runtime, on the first save.
2. **A required field never supplied on read.**  The row loads, the constructor
   runs, and pydantic refuses - or worse, a defaulted field quietly replaces data
   that was stored.

This script checks both statically, by walking the AST of ``repository.py`` and
diffing every attribute access against the ``model_fields`` of the schema the
parameter is bound to.  It exits non-zero on any mismatch so it can gate a commit.

Usage:  python3 scripts/audit_p03_persistence.py
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

import app.opportunities.schemas as S  # noqa: E402
from app.opportunities.repository import MAPPING_GAPS, OpportunityRepository  # noqa: E402

REPO = BACKEND / "app" / "opportunities" / "repository.py"

#: local parameter name -> schema class name, per method
READ_BINDINGS: dict[str, tuple[str, str]] = {
    "_candidate_values": ("candidate", "OpportunityCandidate"),
    "_opportunity_values": ("opportunity", "Opportunity"),
    "_evidence_values": ("ev", "SourceEvidence"),
    "_source_values": ("d", "SourceDescriptor"),
    "save_market_analysis": ("assessment", "MarketAssessment"),
    "save_commercial_analysis": ("assessment", "CommercialAssessment"),
    "save_risk_assessment": ("assessment", "RiskAssessment"),
    "save_report": ("report", "OpportunityReport"),
    "save_competitor_assessment": ("c", "CompetitorProfile"),
}
#: save_risk_assessment binds two different schemas to two names
EXTRA_BINDINGS: dict[str, list[tuple[str, str]]] = {
    "save_scoring_outcome": [
        ("score", "OpportunityScore"),
        ("outcome", "ScoringOutcome"),
        ("validation", "ValidationAssessment"),
    ],
    "save_risk_assessment": [("f", "RiskFinding")],
}
#: _to_x methods and the schema they must fully construct
CONSTRUCTORS: dict[str, str] = {
    "_to_candidate": "OpportunityCandidate",
    "_to_opportunity": "Opportunity",
    "_to_evidence": "SourceEvidence",
}


#: pydantic BaseModel methods and dunders.  These are legitimate attribute
#: accesses on any schema instance but are not fields, so the diff must allow them
#: or it reports a false positive on every model_dump() call.
BASEMODEL_ATTRS = frozenset(
    set(dir(__import__("pydantic").BaseModel))
    | {"model_fields", "model_config", "model_dump", "model_dump_json",
       "model_validate", "model_copy", "model_json_schema"}
)


def _iter_funcs(tree: ast.Module):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield node


def audit_attribute_accesses(tree: ast.Module) -> list[str]:
    problems: list[str] = []
    for func in _iter_funcs(tree):
        bindings = []
        if func.name in READ_BINDINGS:
            var, schema = READ_BINDINGS[func.name]
            bindings.append((var, schema))
        bindings.extend(EXTRA_BINDINGS.get(func.name, []))
        for var, schema in bindings:
            fields = set(getattr(S, schema).model_fields)
            for sub in ast.walk(func):
                if (
                    isinstance(sub, ast.Attribute)
                    and isinstance(sub.value, ast.Name)
                    and sub.value.id == var
                    and sub.attr not in fields
                    and sub.attr not in BASEMODEL_ATTRS
                ):
                    problems.append(
                        f"{func.name}: {var}.{sub.attr} is not a field of {schema}"
                    )
    return sorted(set(problems))


def audit_required_kwargs(tree: ast.Module) -> list[str]:
    """Every required schema field must be passed to the constructor on read."""
    problems: list[str] = []
    for func in _iter_funcs(tree):
        schema_name = CONSTRUCTORS.get(func.name)
        if not schema_name:
            continue
        model = getattr(S, schema_name)
        required = {
            name
            for name, field in model.model_fields.items()
            if field.is_required()
        }
        supplied: set[str] = set()
        for sub in ast.walk(func):
            if isinstance(sub, ast.Call):
                target = sub.func
                name = getattr(target, "id", None) or getattr(target, "attr", None)
                if name in {schema_name, f"{schema_name}Schema", _ALIAS.get(schema_name)}:
                    supplied.update(kw.arg for kw in sub.keywords if kw.arg)
        missing = sorted(required - supplied)
        if missing:
            problems.append(
                f"{func.name}: {schema_name} requires {missing} but the constructor never receives them"
            )
    return sorted(set(problems))


_ALIAS = {"Opportunity": "OpportunitySchema", "OpportunityCandidate": "CandidateSchema"}


def main() -> int:
    tree = ast.parse(REPO.read_bytes().decode("utf-8"))
    invented = audit_attribute_accesses(tree)
    missing = audit_required_kwargs(tree)

    print("P-03 persistence mapping audit")
    print("=" * 62)
    print(f"repository.py                : {REPO.relative_to(BACKEND.parent)}")
    print(f"public repository methods    : "
          f"{len([n for n in dir(OpportunityRepository) if not n.startswith('_')])}")
    print()
    print(f"pydantic BaseModel attrs allowed (not fields): {len(BASEMODEL_ATTRS & set(dir(S.Opportunity)))}")
    print(f"invented attribute accesses  : {len(invented)}")
    for p in invented:
        print(f"   FAIL {p}")
    print(f"unsupplied required fields   : {len(missing)}")
    for p in missing:
        print(f"   FAIL {p}")
    print()
    print("field-coverage diff (verify_mapping_completeness)")
    for name in MAPPING_GAPS["checked"]:
        gaps = MAPPING_GAPS["gaps"].get(name, [])
        print(f"   {'OK  ' if not gaps else 'FAIL'} {name}" + (f": {gaps}" if gaps else ""))
    print()
    clean = not invented and not missing and MAPPING_GAPS["clean"]
    print("RESULT:", "CLEAN - the mapping matches the schemas" if clean else "DEFECTS FOUND")
    return 0 if clean else 1


if __name__ == "__main__":
    raise SystemExit(main())
