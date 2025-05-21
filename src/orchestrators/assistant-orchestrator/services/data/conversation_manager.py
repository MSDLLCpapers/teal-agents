import time
import uuid
from contextlib import nullcontext, contextmanager
import heapq
from ska_utils import get_telemetry

from data.chat_history_manager import ChatHistoryManager
from model import (
    AgentMessage,
    ChatHistory,
    ChatHistoryItem,
    ConversationResponse,
    GeneralResponse,
    MessageType,
    UserMessage,
)
from typing import List, Union


def _chat_history_item_to_message(
    history_item: ChatHistoryItem,
) -> UserMessage | AgentMessage:
    if history_item.message_type == MessageType.USER:
        return UserMessage(content=history_item.message, recipient=history_item.agent_name)
    else:
        return AgentMessage(content=history_item.message, sender=history_item.agent_name)


class ConversationManager:
    def __init__(self, chat_history_manager: ChatHistoryManager):
        self.chat_history_manager = chat_history_manager

    def new_conversation(
        self, orchestrator_name: str, user_id: str, is_resumed: bool
    ) -> ConversationResponse:
        return self._new_conversation(orchestrator_name, user_id, is_resumed)

    def get_conversation(
        self, orchestrator_name: str, user_id: str, conversation_id: str
    ) -> ConversationResponse:
        return self._get_conversation(orchestrator_name, user_id, conversation_id)

    def add_conversation_message(
        self,
        orchestrator_name: str,
        conversation_id: str,
        message_type: MessageType,
        agent_name: str,
        message: str,
    ) -> GeneralResponse:
        self.chat_history_manager.add_session_item(
            orchestrator_name=orchestrator_name,
            session_id=conversation_id,
            item=ChatHistoryItem(
                timestamp=time.time(),
                message_type=message_type,
                agent_name=agent_name,
                message=message,
            ),
        )
        return GeneralResponse(status=200, message="Message added successfully")

    def _get_conversation(
        self, orchestrator_name: str, user_id: str, session_id: str
    ) -> ConversationResponse:
        st = get_telemetry()
        with (
            st.tracer.start_as_current_span("retrieve-session-history")
            if st.telemetry_enabled()
            else nullcontext()
        ):
            messages = self._load_messages(orchestrator_name, user_id, session_id)
        return ConversationResponse(conversation_id=session_id, history=messages)

    def _new_conversation(
        self, orchestrator_name: str, user_id: str, is_resumed: bool
    ) -> ConversationResponse:
        st = get_telemetry()
        previous_session: str | None
        session_id = str(uuid.uuid4())

        @contextmanager
        def create_span(span_name: str):
            """Creates an OpenTelemetry span if telemetry is enabled."""
            if st.telemetry_enabled():
                with st.tracer.start_as_current_span(span_name):
                    yield
            else:
                yield

        if is_resumed:
            # Retrieve previous session ID
            with create_span("retrieve-last-session-id"):
                previous_session = self._get_last_chat_history_id(
                    orchestrator_name,
                    user_id
                )

            with create_span("retrieve-session-history"):
                messages = self._load_messages(
                    orchestrator_name,
                    user_id,
                    previous_session
                )
        else:
            previous_session = None
            messages = []
       
        with create_span("add-chat-history-session"):
            self.chat_history_manager.add_chat_history_session(
                orchestrator_name,
                ChatHistory(
                    user_id=user_id,
                    session_id=session_id,
                    previous_session=previous_session,
                    history=[],
                ),
            )
        with create_span("update-last-session-id"):
            self.chat_history_manager.set_last_session_id_for_user(
                orchestrator_name, user_id, session_id
            )
        return ConversationResponse(conversation_id=session_id, history=messages)

    def _load_messages(
        self, orchestrator_name: str, user_id: str, previous_session: str | None
    ) -> list[Union["UserMessage", "AgentMessage"]]:
        messages: list[Union["UserMessage", "AgentMessage"]] = []
        if previous_session:
            histories: List[List["ChatHistoryItem"]] = self._load_chat_history(
                orchestrator_name,
                user_id,
                previous_session
            )

            # Sort each history if it's not already sorted
            sorted_histories = [
                sorted(history.history, key=lambda x: x.timestamp) for history in histories
            ]

            # Efficiently merge the sorted histories using heapq.merge
            all_items: List["ChatHistoryItem"] = list(
                heapq.merge(*sorted_histories, key=lambda x: x.timestamp)
            )
            for item in all_items:
                messages.append(_chat_history_item_to_message(item))
        return messages

    def _get_last_chat_history_id(self, orchestrator_name: str, user_id: str) -> str | None:
        return self.chat_history_manager.get_last_session_id_for_user(orchestrator_name, user_id)

    def _load_chat_history(
        self, orchestrator_name: str, user_id: str, session_id: str
    ) -> list[ChatHistory]:
        session_chat_history = self._load_chat_history_from_persistence(
            orchestrator_name, user_id, session_id
        )
        if session_chat_history.previous_session:
            previous_histories = self._load_chat_history(
                orchestrator_name, user_id, session_chat_history.previous_session
            )
            previous_histories.append(session_chat_history)
            return previous_histories
        else:
            return [session_chat_history]

    def _load_chat_history_from_persistence(
        self, orchestrator_name: str, user_id: str, session_id: str
    ) -> ChatHistory:
        return self.chat_history_manager.get_chat_history_session(
            orchestrator_name, user_id, session_id
        )
