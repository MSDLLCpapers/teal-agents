import asyncio
import logging

from pynamodb.models import DoesNotExist
from ska_utils import AppConfig, Singleton

from configs import TA_ENVIRONMENT
from data.chat_history_manager import ChatHistoryManager
from model import ChatHistory, ChatHistoryItem, MessageType
from model.dynamo.chat_history import ChatHistory as DynamoChatHistory
from model.dynamo.chat_history_item import ChatHistoryItem as DynamoChatHistoryItem
from model.dynamo.last_chat_session import LastChatSession as DynamoLastChatSession

logger = logging.getLogger(__name__)


class DynamoChatHistoryManager(ChatHistoryManager, metaclass=Singleton):
    def __init__(self):
        cfg = AppConfig()
        if cfg.get(TA_ENVIRONMENT.env_name) == "local":
            if not DynamoChatHistoryItem.exists():
                DynamoChatHistoryItem.create_table(
                    read_capacity_units=1, write_capacity_units=1, wait=True
                )
            if not DynamoChatHistory.exists():
                DynamoChatHistory.create_table(
                    read_capacity_units=1, write_capacity_units=1, wait=True
                )
            if not DynamoLastChatSession.exists():
                DynamoLastChatSession.create_table(
                    read_capacity_units=1, write_capacity_units=1, wait=True
                )

    async def set_last_session_id_for_user(
        self, orchestrator_name: str, user_id: str, session_id: str
    ):
        last_chat_session = DynamoLastChatSession(
            orchestrator=orchestrator_name, user_id=user_id, session_id=session_id
        )
        try:
            await asyncio.to_thread(last_chat_session.save)
        except Exception as e:
            logger.exception(f"Error saving session_id: {session_id} to DB - Error: {e}")
            raise

    async def get_last_session_id_for_user(
        self, orchestrator_name: str, user_id: str
    ) -> str | None:
        try:
            last_chat_session = await asyncio.to_thread(
                DynamoLastChatSession.get, orchestrator_name, user_id
            )
            return last_chat_session.session_id
        except DoesNotExist as e:
            logger.exception(f"Unable to load last session_id for user: {user_id} - Error: {e}")
            raise

    async def get_session_items(
        self, orchestrator_name: str, session_id: str
    ) -> list[ChatHistoryItem]:
        chat_history_items: list[ChatHistoryItem] = []

        def _sync_get_items_and_process():
            dynamo_items = DynamoChatHistoryItem.query(session_id)
            processed_items: list[ChatHistoryItem] = []
            for item in dynamo_items:
                if item.orchestrator != orchestrator_name:
                    continue
                chat_history_item = ChatHistoryItem(
                    timestamp=item.timestamp,
                    agent_name=item.agent_name,
                    message_type=item.message_type,
                    message=item.message,
                )
                processed_items.append(chat_history_item)
            return processed_items

        chat_history_items = await asyncio.to_thread(_sync_get_items_and_process)

        return chat_history_items

    async def add_session_item(
        self, orchestrator_name: str, session_id: str, item: ChatHistoryItem
    ) -> None:
        dynamo_item = DynamoChatHistoryItem(
            session_id=session_id,
            timestamp=item.timestamp,
            orchestrator=orchestrator_name,
            agent_name=item.agent_name,
            message_type=DynamoChatHistoryManager._get_message_type_string(item.message_type),
            message=item.message,
        )
        try:
            await asyncio.to_thread(dynamo_item.save)
        except Exception as e:
            logger.exception(
                f"Error adding session item to session_id: {session_id} in DB - Error: {e}"
            )
            raise

    async def get_chat_history_session(
        self, orchestrator_name: str, user_id: str, session_id: str
    ) -> ChatHistory | None:
        chat_history_items = await self.get_session_items(orchestrator_name, session_id)
        try:
            dynamo_history = await asyncio.to_thread(DynamoChatHistory.get, user_id, session_id)
            if dynamo_history.orchestrator != orchestrator_name:
                return None
            chat_history = ChatHistory(
                user_id=user_id,
                session_id=session_id,
                previous_session=dynamo_history.previous_session,
                history=chat_history_items,
            )
            return chat_history
        except DoesNotExist as e:
            logger.exception(f"Conversation with session_id: {session_id} not found - Error: {e}")
            raise

    async def add_chat_history_session(
        self, orchestrator_name: str, chat_history: ChatHistory
    ) -> None:
        dynamo_history = DynamoChatHistory(
            user_id=chat_history.user_id,
            session_id=chat_history.session_id,
            orchestrator=orchestrator_name,
            previous_session=chat_history.previous_session,
        )
        try:
            await asyncio.to_thread(dynamo_history.save)
        except Exception as e:
            logger.exception(f"Error adding chat history session to DB - Error: {e}")
            raise

    @staticmethod
    def _get_message_type_string(message_type: MessageType) -> str:
        match message_type:
            case MessageType.AGENT:
                return "agent"
            case _:
                return "user"
