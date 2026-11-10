"""P-04 Dynamic Agent Factory package.

Agents are LOGICAL configurations (rows + JSON) sharing the P-02 model
infrastructure — never per-agent processes or model instances. All
creation, permission, lifecycle and scaling decisions in this package are
deterministic policy code (Constitution Article 0; P-04 §§7/8/11/14).
"""
from .service import AgentFactoryService

__all__ = ["AgentFactoryService"]
