from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from ska_types import ExtraData, MultiModalItem, TokenUsage


class UserMessage(BaseModel):
    session_id: str | None = None
    task_id: str | None = None
    items: list[MultiModalItem]


class AgentTaskItem(BaseModel):
    task_id: str
    role: Literal["user", "assistant"]
    item: MultiModalItem
    request_id: str
    updated: datetime


class AgentTask(BaseModel):
    task_id: str
    session_id: str
    user_id: str
    items: list[AgentTaskItem]
    created_at: datetime
    last_updated: datetime
    status: Literal["Running", "Paused", "Completed", "Failed"] = "Running"


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
