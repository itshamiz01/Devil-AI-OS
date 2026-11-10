"""Gate 2 readiness review — inventory scan v2 (audit-only, read-only).

From the application's own metadata, OpenAPI schema and route-module
sources:
  * every table grouped by owning model module
  * a money-column scan over ALL tables, classified by owner module
  * API surface from OpenAPI: paths/operations per route group, and
    which operations are public (no bearer security)
  * per-module permission aliases (require_permission bindings)
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))

from app.database import models as _models  # noqa: F401,E402
from app.database.models.base import Base  # noqa: E402

OUT = Path(__file__).resolve().parent
lines: list[str] = []


def emit(s: str = "") -> None:
    lines.append(s)
    print(s)


tables = Base.metadata.tables
emit(f"METADATA TABLES: {len(tables)} (physical DB adds alembic_version)")

# ---- ownership: table -> model module --------------------------------
owner: dict[str, str] = {}
for mapper in Base.registry.mappers:
    cls = mapper.class_
    owner[mapper.local_table.name] = cls.__module__.rsplit(".", 1)[-1]
by_owner: dict[str, list[str]] = defaultdict(list)
for name in sorted(tables):
    by_owner[owner.get(name, "?")].append(name)
emit("\nTABLES BY OWNING MODEL MODULE:")
for mod in sorted(by_owner):
    emit(f"  models.{mod}: {len(by_owner[mod])} tables")

# ---- money scan, classified by owner ----------------------------------
MONEY_TOKENS = ("amount", "minor", "currency", "price", "balance",
                "revenue", "profit", "collected", "journal", "ledger",
                "charge", "fee")
money_hits: dict[str, list[str]] = {}
for name in sorted(tables):
    hits = [c.name for c in tables[name].columns
            if any(tok in c.name.lower() for tok in MONEY_TOKENS)]
    if hits:
        money_hits[name] = hits
fin_tables = set(by_owner.get("financial", []))
emit(f"\nMONEY-TOKEN SCAN: {len(money_hits)} of {len(tables)} tables have >=1 hit")
emit(f"  owned by models.financial (P-07): "
     f"{sum(1 for t in money_hits if t in fin_tables)}")
emit(f"  owned by other modules: {sum(1 for t in money_hits if t not in fin_tables)}")
emit("\n  NON-P-07 tables with money-token columns (owner: columns):")
for name, cols in sorted(money_hits.items()):
    if name not in fin_tables:
        emit(f"    {name} (models.{owner.get(name)}): {', '.join(cols)}")
emit("\n  journal/ledger columns anywhere outside models.financial:")
jl = [(t, c) for t, cols in money_hits.items() if t not in fin_tables
      for c in cols if "journal" in c or "ledger" in c]
emit(f"    {jl if jl else 'NONE'}")
emit("\n  'collected'/'balance' columns outside models.financial:")
cb = [(t, c) for t, cols in money_hits.items() if t not in fin_tables
      for c in cols if "collected" in c or "balance" in c]
emit(f"    {cb if cb else 'NONE'}")

inv = {name: {"owner_module": owner.get(name),
              "columns": [c.name for c in tables[name].columns]}
       for name in sorted(tables)}
(OUT / "TABLE_INVENTORY.json").write_text(json.dumps(inv, indent=1))

# ---- API surface from OpenAPI -----------------------------------------
from app.core.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402

METHODS = ("get", "post", "put", "patch", "delete")
with tempfile.TemporaryDirectory() as tmp:
    app = create_app(Settings(data_dir=Path(tmp)))
    spec = app.openapi()
paths = spec["paths"]
ops_total = 0
group_paths: dict[str, int] = Counter()
group_ops: dict[str, int] = Counter()
public_ops: list[str] = []
perm_note = []
for p, ops in paths.items():
    seg = p.removeprefix("/api/v1/").split("/")[0] or "(root)"
    group_paths[seg] += 1
    for m, op in ops.items():
        if m not in METHODS:
            continue
        ops_total += 1
        group_ops[seg] += 1
        if not op.get("security"):
            public_ops.append(f"{m.upper()} {p}")
emit(f"\nAPI SURFACE (OpenAPI {spec['openapi']}, info version "
     f"{spec['info']['version']}): {len(paths)} paths, {ops_total} operations")
emit("  security schemes: "
     + json.dumps(spec.get("components", {}).get("securitySchemes", {})))
emit("\n  ROUTE GROUPS (paths / operations):")
for seg in sorted(group_paths):
    emit(f"    /{seg}: {group_paths[seg]} paths, {group_ops[seg]} operations")
emit(f"\n  PUBLIC operations (no bearer security): {len(public_ops)}")
for p in sorted(public_ops):
    emit(f"    {p}")

# ---- permission aliases per route module -------------------------------
emit("\nPERMISSION ALIASES PER ROUTE MODULE (source scan):")
routes_dir = BACKEND / "app" / "api" / "routes"
alias_report: dict[str, dict[str, str]] = {}
for f in sorted(routes_dir.glob("*.py")):
    if f.name == "__init__.py":
        continue
    src = f.read_text()
    aliases = dict(re.findall(
        r"^(\w+)\s*=\s*require_permission\(([^)]+)\)", src, re.M))
    if aliases:
        alias_report[f.stem] = aliases
        emit(f"  {f.stem}: " + "; ".join(f"{k}={v}" for k, v in aliases.items()))
    else:
        emit(f"  {f.stem}: (no require_permission aliases)")

# enum vs literal permission strings
from app.permissions.models import Permission  # noqa: E402
enum_values = {p.value for p in Permission}
emit(f"\nPermission enum members: {len(enum_values)}")
literal_users = [m for m, a in alias_report.items()
                 for v in a.values() if v.startswith('"')]
emit(f"modules binding a permission by raw string literal: {literal_users}")

(OUT / "INVENTORY_EVIDENCE.txt").write_text("\n".join(lines) + "\n")
emit("\nwrote INVENTORY_EVIDENCE.txt, TABLE_INVENTORY.json")
