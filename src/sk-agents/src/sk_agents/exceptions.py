# Standard error handling imports
from sk_agents.error_handling import (
    ERROR_CONFIG_FILE_NOT_FOUND,
    ERROR_HANDLER_INIT_FAILED,
    ERROR_INPUT_EXCEEDS_LIMITS,
    ERROR_INSUFFICIENT_PERMISSIONS,
    ERROR_INVALID_API_VERSION,
    ERROR_INVALID_CONFIG_FORMAT,
    ERROR_INVALID_FILE_PATH,
    ERROR_INVALID_INPUT_FORMAT,
    ERROR_INVALID_PARAMETER_VALUE,
    ERROR_INVALID_STATE_TRANSITION,
    ERROR_INVALID_TOKEN,
    ERROR_INVALID_URL_FORMAT,
    ERROR_MISSING_AUTH_HEADER,
    ERROR_MISSING_ENV_VAR,
    ERROR_MISSING_REQUIRED_FIELD,
    ERROR_MISSING_SERVICE_INFO,
    ERROR_MODEL_INVOCATION_FAILED,
    ERROR_MODEL_NOT_AVAILABLE,
    ERROR_MODEL_TIMEOUT,
    ERROR_PLUGIN_EXECUTION_FAILED,
    ERROR_PLUGIN_NOT_FOUND,
    ERROR_PLUGIN_TIMEOUT,
    ERROR_REQUEST_TIMEOUT,
    ERROR_RESOURCE_LIMIT_EXCEEDED,
    ERROR_SERVICE_UNAVAILABLE,
    ERROR_SESSION_NOT_FOUND,
    ERROR_STATE_PERSISTENCE_FAILED,
    ERROR_STREAMING_ERROR,
    ERROR_TASK_NOT_FOUND,
    ERROR_TOKEN_EXPIRED,
    ERROR_UNEXPECTED_ERROR,
    AgentAuthenticationError,
    AgentConfigurationError,
    AgentException,
    AgentExecutionError,
    AgentResourceError,
    AgentStateError,
    AgentTimeoutError,
    AgentValidationError,
)


# SK Agents Exceptions
class AgentsException(Exception):
    """Base class for all exception in SKagents"""


class InvalidConfigException(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class InvalidInputException(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class AgentInvokeException(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class PersistenceCreateError(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class PersistenceLoadError(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class PersistenceUpdateError(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class PersistenceDeleteError(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class AuthenticationException(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class PluginCatalogDefinitionException(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


class PluginFileReadException(AgentsException):
    message: str

    def __init__(self, message: str):
        self.message = message


# Export all for use by other modules
__all__ = [
    # SK Agents legacy exceptions
    "AgentsException",
    "InvalidConfigException",
    "InvalidInputException",
    "AgentInvokeException",
    "PersistenceCreateError",
    "PersistenceLoadError",
    "PersistenceUpdateError",
    "PersistenceDeleteError",
    "AuthenticationException",
    "PluginCatalogDefinitionException",
    "PluginFileReadException",
    # Modern error handling classes
    "AgentException",
    "AgentConfigurationError",
    "AgentAuthenticationError",
    "AgentValidationError",
    "AgentExecutionError",
    "AgentTimeoutError",
    "AgentResourceError",
    "AgentStateError",
    # Error codes
    "ERROR_MISSING_ENV_VAR",
    "ERROR_INVALID_CONFIG_FORMAT",
    "ERROR_CONFIG_FILE_NOT_FOUND",
    "ERROR_INVALID_API_VERSION",
    "ERROR_MISSING_SERVICE_INFO",
    "ERROR_INVALID_URL_FORMAT",
    "ERROR_INVALID_FILE_PATH",
    "ERROR_MISSING_AUTH_HEADER",
    "ERROR_INVALID_TOKEN",
    "ERROR_TOKEN_EXPIRED",
    "ERROR_INSUFFICIENT_PERMISSIONS",
    "ERROR_MISSING_REQUIRED_FIELD",
    "ERROR_INVALID_INPUT_FORMAT",
    "ERROR_INPUT_EXCEEDS_LIMITS",
    "ERROR_INVALID_PARAMETER_VALUE",
    "ERROR_HANDLER_INIT_FAILED",
    "ERROR_MODEL_INVOCATION_FAILED",
    "ERROR_PLUGIN_EXECUTION_FAILED",
    "ERROR_STREAMING_ERROR",
    "ERROR_UNEXPECTED_ERROR",
    "ERROR_MODEL_NOT_AVAILABLE",
    "ERROR_PLUGIN_NOT_FOUND",
    "ERROR_SERVICE_UNAVAILABLE",
    "ERROR_RESOURCE_LIMIT_EXCEEDED",
    "ERROR_REQUEST_TIMEOUT",
    "ERROR_MODEL_TIMEOUT",
    "ERROR_PLUGIN_TIMEOUT",
    "ERROR_SESSION_NOT_FOUND",
    "ERROR_TASK_NOT_FOUND",
    "ERROR_INVALID_STATE_TRANSITION",
    "ERROR_STATE_PERSISTENCE_FAILED",
]
