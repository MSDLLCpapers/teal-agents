from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ElicitationPending:
    """Stored pending elicitation for a session/task."""
    elicitation_id: str
    mode: str  # "form" or "url"
    url: Optional[str]
    requested_schema: Optional[Dict[str, Any]]
    message: Optional[str]
    server_name: Optional[str]
    user_id: str
    session_id: str
    task_id: str
    request_id: str
    tool_name: Optional[str]
    tool_args: Optional[Dict[str, Any]]


class McpElicitationRequired(Exception):
    """Raised when an MCP tool requires elicitation."""

    def __init__(self, pending: ElicitationPending):
        super().__init__("MCP elicitation required")
        self.pending = pending
