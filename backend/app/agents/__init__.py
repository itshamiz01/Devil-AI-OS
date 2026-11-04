"""P-04 Dynamic Agent Factory: public surface.

**This module must stay import-light.** ``app/database/models.py`` imports
:mod:`app.agents.lifecycle` for the agent status vocabulary, and importing any
submodule of a package executes the package ``__init__`` first. Re-exporting
:mod:`.templates` or :mod:`.subsystem` here therefore pulls in
``app.database.connection`` and ``app.database.repositories`` while ``models``
is still mid-import, and the application fails to start with
``ImportError: cannot import name 'Base' from partially initialized module``.

So the surface re-exported here is exactly the two modules that depend on
nothing but pydantic: the lifecycle graph and the typed schemas. Everything
that touches the database is imported directly from its module, which is also
how P-02 and P-03 are wired::

    from app.agents.subsystem import build_agents
    from app.agents.templates import TemplateService
"""
from .lifecycle import (
    ALLOWED_TRANSITIONS,
    STATES,
    AgentStatus,
    LifecycleTransitionError,
    can_transition,
    is_terminal,
    transition,
)
from .schemas import (
    AgentCapabilityView,
    AgentCreationRequestView,
    AgentPermissionView,
    AgentRecordView,
    AgentTemplateVersionView,
    AgentTemplateView,
    ResourceBudget,
    RetryPolicy,
    TemplateConfiguration,
)

__all__ = [
    "ALLOWED_TRANSITIONS", "STATES", "AgentStatus", "LifecycleTransitionError",
    "can_transition", "is_terminal", "transition",
    "AgentCapabilityView", "AgentCreationRequestView", "AgentPermissionView",
    "AgentRecordView", "AgentTemplateVersionView", "AgentTemplateView",
    "ResourceBudget", "RetryPolicy", "TemplateConfiguration",
]
