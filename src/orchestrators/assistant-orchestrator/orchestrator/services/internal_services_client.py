import uuid
from typing import Dict, List, Optional

from model import Conversation, UserMessage, AgentMessage, ContextItem, ContextType
from services.services_client import (
    ServicesClient,
    MessageType,
    GeneralResponse,
    VerifyTicketResponse,
)


class InternalConversation(Conversation):
    previous_conversation: str | None = None


class InternalServicesClient(ServicesClient):
    def __init__(self):
        self.last_conversation: Dict[str, str] = {}
        self.conversations: Dict[str, InternalConversation] = {}
        self.contexts: Dict[str, Dict[str, str]] = {}

    def new_conversation(self, user_id: str, is_resumed: bool) -> Conversation:
        message_list: List[UserMessage | AgentMessage] = []
        user_context: Dict[str, ContextItem] = {}
        conversation = InternalConversation(
            conversation_id=str(uuid.uuid4()),
            user_id=user_id,
            history=message_list,
            user_context=user_context,
        )
        if is_resumed and user_id in self.last_conversation:
            conversation.previous_conversation = self.last_conversation[user_id]
            previous_conversations = self._get_previous_conversations(user_id)
            for previous_conversation in previous_conversations:
                for message in previous_conversation.history:
                    message_list.append(message)
            conversation.history = message_list
        self.conversations[conversation.conversation_id] = conversation
        self.last_conversation[user_id] = conversation.conversation_id
        print("New conversation id created: {}".format(conversation.conversation_id))
        return conversation
    
    def get_conversation(self, user_id: str, session_id: str) -> Conversation:
        message_list: List[UserMessage | AgentMessage] = []
        user_context: Dict[str, ContextItem] = {}
        conversation = Conversation(
            conversation_id=session_id,
            user_id=user_id,
            history=message_list,
            user_context=user_context,
        )
        previous_conversation = self._get_previous_conversations_for_id(session_id)[0]
        for message in previous_conversation.history:
            message_list.append(message)
        conversation.history = message_list
        return conversation

    def add_conversation_message(
        self,
        conversation_id: str,
        message_type: MessageType,
        agent_name: str,
        message: str,
    ) -> GeneralResponse:
        if message_type == MessageType.AGENT:
            return GeneralResponse(status=200, message="Agent message added successfully")
        elif message_type == MessageType.USER:
            return GeneralResponse(status=200, message="User message added successfully")
        else:
            raise Exception("Failed to add conversation message")

    def verify_ticket(self, ticket: str, ip_address: str) -> VerifyTicketResponse:
        return VerifyTicketResponse(is_valid=True, user_id="default")

    def add_context_item(
        self, user_id: str, item_key: str, item_value: str
    ) -> GeneralResponse:
        if user_id not in self.contexts:
            self.contexts[user_id] = {}
        self.contexts[user_id][item_key] = item_value
        return GeneralResponse(status=200, message="Item added successfully")

    def update_context_item(
        self, user_id: str, item_key: str, item_value: str
    ) -> GeneralResponse:
        if user_id not in self.contexts:
            return GeneralResponse(status=404, message="User not found")
        if item_key not in self.contexts[user_id]:
            return GeneralResponse(status=404, message="Item not found")
        self.contexts[user_id][item_key] = item_value
        return GeneralResponse(status=200, message="Item updated successfully")

    def delete_context_item(self, user_id: str, item_key: str) -> GeneralResponse:
        if user_id not in self.contexts:
            return GeneralResponse(status=404, message="User not found")
        if item_key not in self.contexts[user_id]:
            return GeneralResponse(status=404, message="Item not found")
        del self.contexts[user_id][item_key]
        return GeneralResponse(status=200, message="Item deleted successfully")

    def get_context_items(self, user_id: str) -> Dict[str, str]:
        if user_id not in self.contexts:
            return {}
        return self.contexts[user_id]

    def _get_previous_conversations(self, user_id: str) -> List[InternalConversation]:
        previous_conversations: List[InternalConversation] = []
        if user_id not in self.last_conversation:
            return previous_conversations
        return self._get_previous_conversations_for_id(self.last_conversation[user_id])

    def _get_previous_conversations_for_id(
        self, conversation_id: str
    ) -> List[InternalConversation]:
        conversation = self.conversations[conversation_id]
        if conversation.previous_conversation is None:
            return [conversation]
        else:
            return [conversation] + self._get_previous_conversations_for_id(
                conversation.previous_conversation
            )
