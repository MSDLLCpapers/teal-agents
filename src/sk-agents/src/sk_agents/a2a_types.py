from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

from sk_agents.ska_types import BaseMultiModalInput, InvokeResponse, PartialResponse


class A2AEventType(str, Enum):
    INVOKE = "INVOKE"
    INVOKE_STREAM = "INVOKE_STREAM"
    PARTIAL_RESPONSE = "PARTIAL_RESPONSE"
    FINAL_RESPONSE = "FINAL_RESPONSE"
    EXTRA_DATA = "EXTRA_DATA"
    ERROR = "ERROR"


class A2AInvokeResponse(BaseModel):
    event_id: str
    topic: str


class A2ABaseEvent(BaseModel):
    event_type: A2AEventType
    event_data: Any


class A2AInvokeEvent(A2ABaseEvent):
    event_id: str
    event_type: Literal[A2AEventType.INVOKE, A2AEventType.INVOKE_STREAM] = A2AEventType.INVOKE
    event_data: BaseMultiModalInput


class A2AInvokeStreamEvent(A2ABaseEvent):
    event_type: A2AEventType = A2AEventType.INVOKE_STREAM
    event_data: BaseMultiModalInput


class A2AErrorResponse(BaseModel):
    status_code: int
    detail: str


class A2APartialResponseEvent(A2ABaseEvent):
    event_type: A2AEventType = A2AEventType.PARTIAL_RESPONSE
    event_data: PartialResponse


class A2AInvokeResponseEvent(A2ABaseEvent):
    event_type: A2AEventType = A2AEventType.FINAL_RESPONSE
    event_data: InvokeResponse


class A2AErrorResponseEvent(A2ABaseEvent):
    event_type: A2AEventType = A2AEventType.ERROR
    event_data: A2AErrorResponse


class A2ANonRecoverableError(Exception):
    pass
