from enum import Enum
from typing import TypeVar, Generic

from pydantic import BaseModel, ConfigDict

T = TypeVar("T", bound=BaseModel)


class EventType(Enum):
    PLAN = "plan"
    MANAGER_RESPONSE = "manager-response"
    AGENT_REQUEST = "agent-request"
    ERROR = "error"
    PARTIAL_RESPONSE = "partial-response"
    FINAL_RESPONSE = "final-response"


class EventResponse(BaseModel, Generic[T]):
    event_type: EventType
    data: T


class ErrorResponse(BaseModel):
    session_id: str | None = None
    source: str | None = None
    request_id: str | None = None

    status_code: int
    detail: str


def new_event_response(event_type: EventType, data: T) -> str:
    return f"event: {event_type.value}\ndata: {data.model_dump_json()}\n\n"


class ExtraDataElement(BaseModel):
    key: str
    value: str


class ExtraData(BaseModel):
    items: list[ExtraDataElement]


class TokenUsage(BaseModel):
    completion_tokens: int
    prompt_tokens: int
    total_tokens: int


class InvokeResponse(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="allow", arbitrary_types_allowed=True)

    session_id: str | None = None
    source: str | None = None
    request_id: str | None = None

    token_usage: TokenUsage
    extra_data: ExtraData | None = None
    output_raw: str | None = None
    output_pydantic: T | None = None


class IntermediateTaskResponse(BaseModel):
    task_no: int
    task_name: str
    response: InvokeResponse


class PartialResponse(BaseModel):
    session_id: str | None = None
    source: str | None = None
    request_id: str | None = None

    output_partial: str
