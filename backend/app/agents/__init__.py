"""P-04 Dynamic Agent Factory: public surface."""
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
