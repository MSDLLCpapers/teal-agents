from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict
from semantic_kernel.contents.chat_history import ChatHistory

from sk_agents.ska_types import ExtraData, MultiModalItem, TokenUsage


class UserMessage(BaseModel):
    session_id: str | None = None
    task_id: str | None = None
    items: list[MultiModalItem]
    user_context: dict[str, str] | None = None


class AgentTaskItem(BaseModel):
    task_id: str
    role: Literal["user", "assistant"]
    item: MultiModalItem
    request_id: str
    updated: datetime
    pending_tool_calls: list[dict] | None = None  # Store serialized FunctionCallContent
    chat_history: ChatHistory | None = None


class AgentTask(BaseModel):
    task_id: str
    session_id: str
    user_id: str
    items: list[AgentTaskItem]
    created_at: datetime
    last_updated: datetime
    status: Literal["Running", "Paused", "Completed", "Failed", "Canceled"] = "Running"


class TealAgentsResponse(BaseModel):
    session_id: str
    task_id: str
    request_id: str
    output: str
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)
    source: str | None = None
    token_usage: TokenUsage
    extra_data: ExtraData | None = None


class TealAgentsPartialResponse(BaseModel):
    session_id: str
    task_id: str
    request_id: str
    output_partial: str
    source: str | None = None


class HitlResponse(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    message: str = "Human intervention required."
    approval_url: str
    rejection_url: str
    tool_calls: list[dict]  # Serialized FunctionCallContent


class RejectedToolResponse(BaseModel):
    task_id: str
    session_id: str
    request_id: str
    message: str = "Tool excecution rejected."


class StateResponse(BaseModel):
    session_id: str
    task_id: str
    request_id: str
    status: Literal["Running", "Paused", "Completed", "Failed"]
    content: str | dict | None = None
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)


class TaskStatus(Enum):
    """Enum representing the status of a task"""
    RUNNING = "Running"
    PAUSED = "Paused"
    COMPLETED = "Completed"
    FAILED = "Failed"
