"""Agent architecture, bounded state machine, read-only tools, and concurrency coordinator."""

from adam.agent.tools import (
    ReadOnlyToolRegistry,
    ForbiddenToolError,
)
from adam.agent.redaction import (
    SecretRedactor,
)
from adam.agent.budget import (
    EnvironmentProfile,
    ResourceBudgetManager,
    MACBOOK_AIR_8GB_PROFILE,
    DEV_SERVER_PROFILE,
    GOV_PRODUCTION_PROFILE,
)
from adam.agent.coordinator import (
    HeavyWorkerCoordinator,
    HeavyTaskType,
    ResourceContentionError,
)
from adam.agent.state_machine import (
    BoundedAgentStateMachine,
    AgentResponse,
    AgentStateTransition,
    TaskSelfExpansionError,
)

__all__ = [
    "ReadOnlyToolRegistry",
    "ForbiddenToolError",
    "SecretRedactor",
    "EnvironmentProfile",
    "ResourceBudgetManager",
    "MACBOOK_AIR_8GB_PROFILE",
    "DEV_SERVER_PROFILE",
    "GOV_PRODUCTION_PROFILE",
    "HeavyWorkerCoordinator",
    "HeavyTaskType",
    "ResourceContentionError",
    "BoundedAgentStateMachine",
    "AgentResponse",
    "AgentStateTransition",
    "TaskSelfExpansionError",
]
