"""Scaling policy (§14): deterministic evaluation of whether agent
capacity should change. The policy NEVER claims revenue from internal
task completion; economic figures are estimates with stated inputs, and
``expected_business_benefit`` stays null unless a measurable figure is
supplied by the caller from real business records.
"""
from __future__ import annotations

DECISIONS = (
    "KEEP_CURRENT_CAPACITY", "REASSIGN_WORK", "INCREASE_CONCURRENCY",
    "CREATE_SPECIALIZED_AGENT", "QUEUE_WORK", "REDUCE_AGENT_COUNT",
    "REQUEST_OWNER_APPROVAL",
)


class ScalingPolicy:
    @staticmethod
    def evaluate(snapshot: dict, settings: dict) -> dict:
        """snapshot keys (all measured by the caller):
        queue_depth, active_agents, busy_agents, idle_agents,
        pressure_level, specialized_demand (bool), at_agent_ceiling (bool),
        avg_task_seconds (float|None), pending_tasks (int)."""
        queue_depth = int(snapshot.get("queue_depth") or 0)
        active = int(snapshot.get("active_agents") or 0)
        busy = int(snapshot.get("busy_agents") or 0)
        idle = int(snapshot.get("idle_agents") or 0)
        pressure = int(snapshot.get("pressure_level") or 0)
        factors: list[str] = []
        decision: str

        if pressure >= 2:
            decision = "QUEUE_WORK"
            factors.append("resource pressure level 2: new capacity would worsen contention")
            if idle > 0 and queue_depth == 0:
                decision = "REDUCE_AGENT_COUNT"
                factors.append("idle agents exist under pressure with an empty queue: suspend idle agents")
        elif queue_depth == 0:
            if active > 0 and busy == 0 and idle == active:
                decision = "REDUCE_AGENT_COUNT"
                factors.append("no queued work and every active agent is idle")
            else:
                decision = "KEEP_CURRENT_CAPACITY"
                factors.append("no queued work; current capacity is sufficient")
        elif idle > 0:
            decision = "REASSIGN_WORK"
            factors.append(f"{queue_depth} task(s) queued while {idle} agent(s) are idle")
        elif snapshot.get("specialized_demand"):
            if snapshot.get("at_agent_ceiling"):
                decision = "REQUEST_OWNER_APPROVAL"
                factors.append("specialized demand exists but the agent ceiling is reached; "
                               "raising it is an owner decision")
            else:
                decision = "CREATE_SPECIALIZED_AGENT"
                factors.append("queued work needs specialization no current agent holds, "
                               "and the ceiling permits a new agent")
        elif busy >= active and active > 0:
            decision = "INCREASE_CONCURRENCY"
            factors.append("all agents busy with work queued; per-agent concurrency "
                           "headroom is the cheapest capacity")
        else:
            decision = "KEEP_CURRENT_CAPACITY"
            factors.append("queued work is within current capacity")

        avg = snapshot.get("avg_task_seconds")
        economic = {
            "expected_workload_tasks": queue_depth,
            "estimated_time_savings_seconds": (
                round(avg * queue_depth, 2) if isinstance(avg, (int, float)) else None),
            "estimated_inference_cost": 0.0 if snapshot.get("local_only", True) else None,
            "estimation_basis": ("measured average task duration x queued tasks"
                                 if isinstance(avg, (int, float))
                                 else "unavailable: no measured task durations yet"),
            "expected_business_benefit": None,
            "benefit_note": ("internal task completion is not revenue; no business "
                             "benefit is claimed without collected-revenue evidence"),
        }
        return {"decision": decision, "factors": factors,
                "snapshot": snapshot, "economic_justification": economic}
