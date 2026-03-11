class AgentsException(Exception):
    """Base class for all exception in SKagents"""


class InvalidConfigException(AgentsException):
    """Exception raised when the provided configuration is invalid"""

    message: str

    def __init__(self, message: str):
        self.message = message


class InvalidInputException(AgentsException):
    """Exception raised when the provided input type is invalid"""

    message: str

    def __init__(self, message: str):
        self.message = message


class AgentInvokeException(AgentsException):
    """Exception raised when invoking an Agent failed"""

    message: str

    def __init__(self, message: str):
        self.message = message


class AgentUnavailableException(AgentsException):
    """Exception raised when a target agent is unreachable (connection refused, DNS failure, timeout)."""

    agent_name: str
    message: str

    def __init__(self, agent_name: str, message: str):
        self.agent_name = agent_name
        self.message = message
        super().__init__(f"Agent '{agent_name}' is unavailable: {message}")


class LLMAuthenticationException(AgentsException):
    """Exception raised when the LLM provider rejects authentication (invalid API key, expired token, etc.)."""

    status_code: int
    message: str

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"LLM authentication failed (HTTP {status_code}): {message}")


class LLMServiceException(AgentsException):
    """Exception raised for LLM service-level errors (rate limits, server errors, model not found, etc.)."""

    error_type: str
    message: str
    status_code: int | None

    def __init__(self, error_type: str, message: str, status_code: int | None = None):
        self.error_type = error_type
        self.message = message
        self.status_code = status_code
        super().__init__(f"LLM service error ({error_type}): {message}")


class PersistenceCreateError(AgentsException):
    """Exception raised for errors during task creation."""

    message: str

    def __init__(self, message: str):
        self.message = message


class PersistenceLoadError(AgentsException):
    """Exception raised for errors during task loading."""

    message: str

    def __init__(self, message: str):
        self.message = message


class PersistenceUpdateError(AgentsException):
    """Exception raised for errors during task update."""

    message: str

    def __init__(self, message: str):
        self.message = message


class PersistenceDeleteError(AgentsException):
    """Exception raised for errors during task deletion."""

    message: str

    def __init__(self, message: str):
        self.message = message


class AuthenticationException(AgentsException):
    """Exception raised errors when authenticating users"""

    message: str

    def __init__(self, message: str):
        self.message = message


class PluginCatalogDefinitionException(AgentsException):
    """Exception raised when the parsed json does not match the PluginCatalogDefinition Model"""

    message: str

    def __init__(self, message: str):
        self.message = message


class PluginFileReadException(AgentsException):
    """Raise this exception when the plugin file fails to be read"""

    message: str

    def __init__(self, message: str):
        self.message = message
