from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class MessageType(Enum):
    USER = "user"
    AGENT = "agent"


class NewConversationRequest(BaseModel):
    user_id: str
    is_resumed: bool | None = None


class GetConversationRequest(BaseModel):
    user_id: str
    session_id: str


class AddConversationMessageRequest(BaseModel):
    message_type: MessageType
    agent_name: str
    message: str


class AddContextItemRequest(BaseModel):
    item_key: str
    item_value: str


class UpdateContextItemRequest(BaseModel):
    item_value: str


class CreateTicketRequest(BaseModel, Generic[T]):
    payload: T


class UserIdOnlyRequest(BaseModel):
    user_id: str


class UserIdOnlyCreateTicketRequest(CreateTicketRequest[UserIdOnlyRequest]):
    pass


class VerifyTicketRequest(BaseModel):
    ticket: str
    ip_address: str
