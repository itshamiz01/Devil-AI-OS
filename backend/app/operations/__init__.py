"""P-12 Autonomous Operations Engine.

Coordinates governed autonomous work on top of the accepted stack:
P-02 plans / deterministic templates → §22 pipeline → P-10 broker
authorization → P-01 approvals → P-07 budgets → P-01/P-05 execution
→ independent verification → P-09 learning. See
``docs/autonomous-operations/P12_PRE_IMPLEMENTATION_AUDIT.md``.
"""
from .service import OperationsService

__all__ = ["OperationsService"]
