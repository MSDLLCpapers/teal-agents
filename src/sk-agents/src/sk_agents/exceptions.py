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
