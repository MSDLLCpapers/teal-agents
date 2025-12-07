"""Utilities to handle MCP elicitation pause/resume."""

import json
from typing import Any, Dict

from sk_agents.mcp_elicitation_models import ElicitationPending, McpElicitationRequired


async def persist_and_raise_elicitation(discovery_manager, pending: ElicitationPending):
    """Persist pending elicitation then raise McpElicitationRequired."""
    if discovery_manager:
        await discovery_manager.store_pending_elicitation(
            pending.user_id,
            pending.session_id,
            pending.elicitation_id,
            _pending_to_dict(pending),
        )
    raise McpElicitationRequired(pending)


def _pending_to_dict(pending: ElicitationPending) -> Dict[str, Any]:
    return {
        "elicitation_id": pending.elicitation_id,
        "mode": pending.mode,
        "url": pending.url,
        "requested_schema": pending.requested_schema,
        "message": pending.message,
        "server_name": pending.server_name,
        "user_id": pending.user_id,
        "session_id": pending.session_id,
        "task_id": pending.task_id,
        "request_id": pending.request_id,
        "tool_name": pending.tool_name,
        "tool_args": pending.tool_args,
    }
