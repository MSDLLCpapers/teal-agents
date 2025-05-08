from context_directive import ContextDirective, ContextDirectiveOp
from model import ContextItem, ContextType, Conversation
from services import MessageType, new_client


class ConversationManager:
    def __init__(self, service_name: str):
        self.services_client = new_client(service_name)

    def new_conversation(self, user_id: str, is_resumed: bool) -> Conversation:
        return self.services_client.new_conversation(user_id, is_resumed)

    def get_conversation(self, user_id: str, session_id: str) -> Conversation:
        return self.services_client.get_conversation(user_id, session_id)

    def get_last_response(self, conversation: Conversation):
        return Conversation(
            conversation_id=conversation.conversation_id,
            user_id=conversation.user_id,
            history=(
                conversation.history[-2:]
                if len(conversation.history) >= 2
                else conversation.history
            ),
            user_context=conversation.user_context,
        )

    def add_user_message(self, conversation: Conversation, content: str, recipient: str) -> None:
        self.services_client.add_conversation_message(
            conversation_id=conversation.conversation_id,
            message_type=MessageType.USER,
            agent_name=recipient,
            message=content,
        )
        conversation.add_user_message(content, recipient)

    def add_agent_message(self, conversation: Conversation, content: str, sender: str) -> None:
        self.services_client.add_conversation_message(
            conversation_id=conversation.conversation_id,
            message_type=MessageType.AGENT,
            agent_name=sender,
            message=content,
        )
        conversation.add_agent_message(content, sender)

    def process_context_directives(
        self, conversation: Conversation, directives: list[ContextDirective]
    ):
        for directive in directives:
            match directive.op:
                case ContextDirectiveOp.SET:
                    self.upsert_context_item(conversation, directive.key, directive.value)
                case ContextDirectiveOp.ADD:
                    self.add_context_item(
                        conversation,
                        directive.key,
                        directive.value,
                        directive.type,
                    )
                case ContextDirectiveOp.UPDATE:
                    self.update_context_item(conversation, directive.key, directive.value)
                case ContextDirectiveOp.DELETE:
                    self.delete_context_item(conversation, directive.key)

    def add_context_item(
        self,
        conversation: Conversation,
        item_key: str,
        item_value: str | None,
        context_type: ContextType | None,
    ) -> None:
        item = conversation.add_context_item(item_key, item_value, context_type)
        if item.context_type == ContextType.PERSISTENT:
            self.services_client.add_context_item(conversation.user_id, item_key, item_value)

    def update_context_item(
        self, conversation: Conversation, item_key: str, item_value: str | None
    ) -> None:
        item = conversation.update_context_item(item_key, item_value)
        if item.context_type == ContextType.PERSISTENT:
            self.services_client.update_context_item(conversation.user_id, item_key, item_value)

    def delete_context_item(self, conversation: Conversation, item_key: str) -> None:
        item = conversation.delete_context_item(item_key)
        if item.context_type == ContextType.PERSISTENT:
            self.services_client.delete_context_item(conversation.user_id, item_key)

    def upsert_context_item(self, conversation: Conversation, key: str, value: str | None) -> None:
        try:
            self.update_context_item(conversation, key, value)
        except ValueError:
            self.add_context_item(conversation, key, value, ContextType.TRANSIENT)

    def add_transient_context(
        self, conversation: Conversation, transient_user_context: dict | None
    ) -> None:
        if transient_user_context:
            transient_context = {}
            for key, value in transient_user_context.items():
                transient_context[key] = ContextItem(
                    value=str(value), context_type=ContextType.TRANSIENT
                )
            conversation.user_context.update(transient_context)
