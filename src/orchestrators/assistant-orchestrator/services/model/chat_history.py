
from pydantic import BaseModel

from model.requests import MessageType


class ChatHistoryItem(BaseModel):
    timestamp: float
    message_type: MessageType
    agent_name: str
    message: str


class ChatHistory(BaseModel):
    user_id: str
    session_id: str
    previous_session: str | None
    history: list[ChatHistoryItem]
