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