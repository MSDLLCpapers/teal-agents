from enum import Enum
from typing import List, Literal

from pydantic import BaseModel


class ChatHistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatHistory(BaseModel):
    chat_history: List[ChatHistoryItem]


class ContentType(Enum):
    IMAGE = "image"
    TEXT = "text"


class MultiModalItem(BaseModel):
    content_type: ContentType = ContentType.TEXT
    content: str


class HistoryMultiModalMessage(BaseModel):
    role: Literal["user", "assistant"]
    items: list[MultiModalItem]


class BaseMultiModalInput(BaseModel):
    session_id: str | None = None

    chat_history: list[HistoryMultiModalMessage] | None = None
