"""Survival and Scaling Engine (P-08).

Reads financial truth ONLY through P-07 (§6.1/§32 rule 3), overlays
health/operational state on P-06's lifecycle (never a second state
machine, §5.1), enforces pre-declared experiments with hard
stop-loss (§9), structural autonomy governance (§3.3/§20.2/§25.1)
and preserves failed experiments and closure history permanently.
"""
from .service import SurvivalService

__all__ = ["SurvivalService"]
