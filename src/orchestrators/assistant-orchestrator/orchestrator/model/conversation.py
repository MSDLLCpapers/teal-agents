from enum import Enum

from pydantic import BaseModel


class ContextType(str, Enum):
    TRANSIENT = "transient"
    PERSISTENT = "persistent"


class ContextItem(BaseModel):
    context_type: ContextType
    value: str


class UserMessage(BaseModel):
    content: str
    recipient: str


class AgentMessage(BaseModel):
    content: str
    sender: str


class Conversation(BaseModel):
    conversation_id: str
    user_id: str
    history: list[UserMessage | AgentMessage]
    user_context: dict[str, ContextItem]

    def add_user_message(self, content: str, recipient: str):
        self.history.append(UserMessage(content=content, recipient=recipient))

    def add_agent_message(self, content: str, sender: str):
        self.history.append(AgentMessage(content=content, sender=sender))

    def add_context_item(
        self, item_key: str, item_value: str | None, context_type: ContextType | None
    ) -> ContextItem:
        if item_key in self.user_context:
            raise ValueError(f"Context item already exists - {item_key}")
        self.user_context[item_key] = ContextItem(context_type=context_type, value=item_value)
        return self.user_context[item_key]

    def update_context_item(self, item_key: str, item_value: str | None) -> ContextItem:
        if item_key not in self.user_context:
            raise ValueError(f"Context item does not exist - {item_key}")
        if item_value is None:
            return self.delete_context_item(item_key)
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


class SseMessage(BaseModel):
    task: str
    message: str


class SseFinalMessage(BaseModel):
    conversation: Conversation


class SseError(BaseModel):
    error: str


class SseEventType(Enum):
    AGENT_SELECTOR_RESPONSE = "agent-selector-response"
    INTERMEDIATE_TASK_RESPONSE = "intermediate-task-response"
    ORCH_FINAL_RESPONSE = "orchestrator-final-response"
    UNKNOWN = "unknown"
