from enum import Enum
from typing import List, Dict

from pydantic import BaseModel


class ContextType(Enum):
    TRANSIENT = "transient"
    PERSISTENT = "persistent"


class ContextItem(BaseModel):
    context_type: ContextType
    value: str

class AddContextItemRequest(BaseModel):
    item_key: str
    item_value: str

class UserMessage(BaseModel):
    content: str
    recipient: str


class AgentMessage(BaseModel):
    content: str
    sender: str


class Conversation(BaseModel):
    conversation_id: str
    user_id: str
    history: List[UserMessage | AgentMessage]
    user_context: Dict[str, ContextItem]

    def add_user_message(self, content: str, recipient: str):
        self.history.append(UserMessage(content=content, recipient=recipient))

    def add_agent_message(self, content: str, sender: str):
        self.history.append(AgentMessage(content=content, sender=sender))

    def add_context_item(
        self, item_key: str, item_value: str, context_type: ContextType
    ) -> ContextItem:
        if item_key in self.user_context:
            raise ValueError(f"Context item already exists - {item_key}")
        self.user_context[item_key] = ContextItem(
            context_type=context_type, value=item_value
        )
        return self.user_context[item_key]

    def update_context_item(self, item_key: str, item_value: str) -> ContextItem:
        if item_key not in self.user_context:
            raise ValueError(f"Context item does not exist - {item_key}")
        self.user_context[item_key].value = item_value
        return self.user_context[item_key]

    def delete_context_item(self, item_key: str) -> ContextItem:
        if item_key not in self.user_context:
            raise ValueError(f"Context item does not exist - {item_key}")
        del_item = self.user_context[item_key]
        del self.user_context[item_key]
        return del_item

    def upsert_context_item(self, key: str, value: str) -> ContextItem:
        try:
            return self.update_context_item(key, value)
        except ValueError:
            return self.add_context_item(key, value, ContextType.TRANSIENT)
