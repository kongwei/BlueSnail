"""Framework exceptions."""


class AgentError(Exception):
    """Base exception for the agent framework."""


class ToolNotFoundError(AgentError):
    """Raised when a requested tool is not registered."""


class ToolExecutionError(AgentError):
    """Raised when tool execution fails."""


class ContextOverflowError(AgentError):
    """Raised when context cannot fit within the token budget."""


class SchedulerError(AgentError):
    """Raised when the scheduler encounters an unrecoverable error."""
