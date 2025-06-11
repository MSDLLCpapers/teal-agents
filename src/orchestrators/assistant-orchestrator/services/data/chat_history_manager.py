from abc import ABC, abstractmethod

from model import ChatHistory, ChatHistoryItem


class ChatHistoryManager(ABC):
    @abstractmethod
    async def set_last_session_id_for_user(
        self, orchestrator_name: str, user_id: str, session_id: str
    ):
        pass

    @abstractmethod
    async def get_last_session_id_for_user(
        self, orchestrator_name: str, user_id: str
    ) -> str | None:
        pass

    @abstractmethod
    async def get_session_items(
        self, orchestrator_name: str, session_id: str
    ) -> list[ChatHistoryItem]:
        pass

    @abstractmethod
    async def add_session_item(
        self, orchestrator_name: str, session_id: str, item: ChatHistoryItem
    ):
        pass

    @abstractmethod
    async def get_chat_history_session(
        self, orchestrator_name: str, user_id: str, session_id: str
    ) -> ChatHistory | None:
        pass

    @abstractmethod
    async def add_chat_history_session(
        self, orchestrator_name: str, chat_history: ChatHistory
    ) -> None:
        pass
