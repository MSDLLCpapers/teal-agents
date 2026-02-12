from abc import ABC, abstractmethod
from enum import StrEnum

from pydantic import BaseModel

from model import Conversation


class MessageType(StrEnum):
    USER = "user"
    AGENT = "agent"


class GeneralResponse(BaseModel):
    status: int
    message: str


class UserNotFoundResponse(GeneralResponse):
    def __init__(self):
        super().__init__(status=404, message="User not found")


class ItemNotFoundResponse(GeneralResponse):
    def __init__(self):
        super().__init__(status=404, message="Item not found")


class ItemUpdatedResponse(GeneralResponse):
    def __init__(self):
        super().__init__(status=200, message="Item updated successfully")


class ItemDeleteResponse(GeneralResponse):
    def __init__(self):
        super().__init__(status=200, message="Item deleted successfully")


class ItemAddedResponse(GeneralResponse):
    def __init__(self):
        super().__init__(status=200, message="Item added successfully")


class AgentMessageResponse(GeneralResponse):
    def __init__(self):
        super().__init__(status=200, message="Agent message added successfully")


class UserMessageResponse(GeneralResponse):
    def __init__(self):
        super().__init__(status=200, message="User message added successfully")


class VerifyTicketResponse(BaseModel):
    is_valid: bool
    user_id: str | None = None


class ServicesClient(ABC):
    @abstractmethod
    async def new_conversation(self, user_id: str, is_resumed: bool) -> Conversation:
        pass

    @abstractmethod
    async def get_conversation(self, user_id: str, session_id: str) -> Conversation:
        pass

    @abstractmethod
    async def add_conversation_message(
        self,
        conversation_id: str,
        message_type: MessageType,
        agent_name: str,
        message: str,
    ) -> GeneralResponse:
        pass

    @abstractmethod
    async def verify_ticket(self, ticket: str, ip_address: str) -> VerifyTicketResponse:
        pass

    @abstractmethod
    async def add_context_item(
        self, user_id: str, item_key: str, item_value: str | None
    ) -> GeneralResponse:
        pass

    @abstractmethod
    async def update_context_item(
        self, user_id: str, item_key: str, item_value: str | None
    ) -> GeneralResponse:
        pass

    @abstractmethod
    async def delete_context_item(self, user_id: str, item_key: str) -> GeneralResponse:
        pass

    @abstractmethod
    async def get_context_items(self, user_id: str) -> dict[str, str | None]:
        pass
