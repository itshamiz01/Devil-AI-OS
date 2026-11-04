#!/usr/bin/env python3
"""Read-only audit: does the documentation match the real configuration surface?

Enforces two P-01 requirements mechanically instead of by eye:

* §5  "Document every important configuration variable."
* §17 "Documentation must reflect the actual implementation."

It cross-checks three things:

1. every ``Settings`` field appears in ``docs/architecture/CONFIGURATION_REFERENCE.md``;
2. every ``AUTONOMUS_*`` key advertised in ``.env.example`` either maps to a real
   ``Settings`` field or is listed in ``KNOWN_INERT`` with a reason;
3. no ``AUTONOMUS_*`` key is documented that does not exist.

An inert key is only tolerated while it is *labelled* inert in ``.env.example``,
because an unlabelled setting that silently does nothing is indistinguishable
from a working one (see D-15).

Read-only: imports the application, reads two files, writes nothing.
Exit code 0 means consistent, 1 means a documented/actual mismatch.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "backend"))

from app.core.config import Settings  # noqa: E402

REFERENCE = REPO / "docs" / "architecture" / "CONFIGURATION_REFERENCE.md"
ENV_EXAMPLE = REPO / ".env.example"

# Derived from the authoritative source, never retyped: a single
# misspelled character in this literal once made the whole audit
# fail silently, reporting every variable as undocumented.
PREFIX = Settings.model_config["env_prefix"]

# Keys intentionally present in .env.example without being Settings fields.
# Each must be labelled inert in the file itself.
KNOWN_INERT = {
    PREFIX + "OPERATING_MODE": "D-15 pending: P-01 implements no operating modes",
}


def main() -> int:
    fields = set(Settings.model_fields)
    problems: list[str] = []

    reference = REFERENCE.read_text(encoding="utf-8")
    documented = set(re.findall(r"`(" + re.escape(PREFIX) + r"[A-Z0-9_]+)`", reference))

    missing_docs = sorted(
        f for f in fields if f"{PREFIX}{f.upper()}" not in documented
    )
    if missing_docs:
        problems.append(
            f"{len(missing_docs)} Settings field(s) undocumented in {REFERENCE.name}: "
            + ", ".join(missing_docs)
        )

    ghost_docs = sorted(
        d for d in documented
        if d[len(PREFIX):].lower() not in fields and d not in KNOWN_INERT
    )
    if ghost_docs:
        problems.append(
            f"{len(ghost_docs)} documented variable(s) are not Settings fields: "
            + ", ".join(ghost_docs)
        )

    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    env_keys: list[str] = []
    for line in env_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        env_keys.append(stripped.split("=", 1)[0].strip())

    for key in env_keys:
        if not key.startswith(PREFIX):
            problems.append(f"{ENV_EXAMPLE.name}: unexpected key without prefix: {key}")
            continue
        stem = key[len(PREFIX):].lower()
        if stem in fields:
            continue
        if key in KNOWN_INERT:
            # Tolerated only if the file itself says so near the key.
            idx = env_text.find(key)
            window = env_text[max(0, idx - 400):idx].lower()
            if "inert" not in window:
                problems.append(
                    f"{ENV_EXAMPLE.name}: {key} is inert but is not labelled inert "
                    "in a preceding comment (an unlabelled no-op reads as a working control)"
                )
            continue
        problems.append(f"{ENV_EXAMPLE.name}: {key} is not a Settings field and is not a known inert key")

    print(f"Settings fields           : {len(fields)}")
    print(f"documented in reference   : {len(documented & {f'{PREFIX}{f.upper()}' for f in fields})}")
    print(f"keys in .env.example      : {len(env_keys)}")
    print(f"known inert (labelled)    : {sorted(KNOWN_INERT)}")

    if problems:
        print("\nPROBLEMS:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    print("\nOK: configuration documentation matches the implemented surface.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
