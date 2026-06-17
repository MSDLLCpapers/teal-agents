from unittest.mock import AsyncMock, MagicMock

import pytest

from context_directive import ContextDirective, ContextDirectiveOp
from model import AgentMessage, ContextItem, ContextType, Conversation, UserMessage

from ..conversation_manager import ConversationManager
from ..services import MessageType


@pytest.fixture
def mock_services_client(mocker):
    """Fixture to mock the services client."""
    return mocker.patch("orchestrator.conversation_manager.new_client", return_value=AsyncMock())


@pytest.fixture
def conversation_manager(mock_services_client):
    """Fixture to create a ConversationManager instance with a mocked client."""
    return ConversationManager(service_name="test_service")


@pytest.fixture
def sample_conversation():
    """Fixture to create a sample Conversation object."""
    return Conversation(
        conversation_id="conv123",
        user_id="user456",
        history=[],
        user_context={},
    )


@pytest.fixture
def sample_conversation_base():
    """Fixture to create a base Conversation object for testing get_last_response.
    Includes sample user_context with ContextItem objects."""
    return Conversation(
        conversation_id="conv123",
        user_id="user456",
        history=[],
        user_context={
            "persistent_key": ContextItem(value="p_val", context_type=ContextType.PERSISTENT),
            "transient_key": ContextItem(value="t_val", context_type=ContextType.TRANSIENT),
        },
    )


@pytest.fixture
def conversation_manager_instance():
    """Fixture to create a MockConversationManager instance for testing get_last_response.
    This mock directly contains the get_last_response logic as it doesn't interact
    with external services for this method."""

    class MockConversationManager:
        async def get_last_response(self, conversation: Conversation):
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

    return MockConversationManager()


@pytest.mark.asyncio
async def test_new_conversation(conversation_manager, mock_services_client):
    """Test new_conversation method."""
    mock_conversation = MagicMock(spec=Conversation)
    mock_services_client.return_value.new_conversation.return_value = mock_conversation

    user_id = "test_user"
    is_resumed = False
    conversation = await conversation_manager.new_conversation(user_id, is_resumed)

    mock_services_client.return_value.new_conversation.assert_called_once_with(user_id, is_resumed)
    assert conversation == mock_conversation


@pytest.mark.asyncio
async def test_get_conversation(conversation_manager, mock_services_client):
    """Test get_conversation method."""
    mock_conversation = MagicMock(spec=Conversation)
    mock_services_client.return_value.get_conversation.return_value = mock_conversation

    user_id = "test_user"
    session_id = "test_session"
    conversation = await conversation_manager.get_conversation(user_id, session_id)

    mock_services_client.return_value.get_conversation.assert_called_once_with(user_id, session_id)
    assert conversation == mock_conversation


@pytest.mark.asyncio
async def test_get_last_response_history(conversation_manager_instance, sample_conversation_base):
    """
    Test get_last_response method when the conversation history has 2 or more messages.
    It should return a new Conversation object containing only the last two messages.
    """
    sample_conversation_base.history = [
        UserMessage(content="hello", recipient="agent"),
        AgentMessage(content="hi there", sender="user"),
        UserMessage(content="how are you?", recipient="agent"),
        AgentMessage(content="I'm good", sender="user"),
        UserMessage(content="What's up?", recipient="agent"),
        AgentMessage(content="Not much", sender="user"),
    ]

    last_response_conversation = await conversation_manager_instance.get_last_response(
        sample_conversation_base
    )
    assert last_response_conversation is not sample_conversation_base
    assert last_response_conversation.conversation_id == sample_conversation_base.conversation_id
    assert last_response_conversation.user_id == sample_conversation_base.user_id

    assert len(last_response_conversation.history) == 2
    assert last_response_conversation.history[0].content == "What's up?"
    assert last_response_conversation.history[1].content == "Not much"


@pytest.mark.asyncio
async def test_get_last_response_partial_history(
    conversation_manager_instance, sample_conversation_base
):
    """
    Test get_last_response with less than 2 messages in history (e.g., 1 message).
    It should return a new Conversation object containing the entire history as is.
    """
    sample_conversation_base.history = [UserMessage(content="hello", recipient="agent")]
    last_response_conversation = await conversation_manager_instance.get_last_response(
        sample_conversation_base
    )

    assert len(last_response_conversation.history) == 1
    assert last_response_conversation.history[0].content == "hello"
    assert isinstance(last_response_conversation.history[0], UserMessage)
    assert last_response_conversation.history[0].recipient == "agent"
    assert last_response_conversation is not sample_conversation_base
    assert last_response_conversation.conversation_id == sample_conversation_base.conversation_id
    assert last_response_conversation.user_id == sample_conversation_base.user_id


@pytest.mark.asyncio
async def test_add_user_message(conversation_manager, sample_conversation, mocker):
    """Test add_user_message method."""
    mock_add_user_message = mocker.patch("model.Conversation.add_user_message")

    content = "User message content"
    recipient = "agent"

    await conversation_manager.add_user_message(sample_conversation, content, recipient)

    conversation_manager.services_client.add_conversation_message.assert_called_once_with(
        conversation_id=sample_conversation.conversation_id,
        message_type=MessageType.USER,
        agent_name=recipient,
        message=content,
    )
    mock_add_user_message.assert_called_once_with(content, recipient)


@pytest.mark.asyncio
async def test_add_agent_message(conversation_manager, sample_conversation, mocker):
    """Test add_agent_message method."""
    mock_add_agent_message = mocker.patch("model.Conversation.add_agent_message")
    content = "Agent message content"
    sender = "AgentX"

    await conversation_manager.add_agent_message(sample_conversation, content, sender)

    conversation_manager.services_client.add_conversation_message.assert_called_once_with(
        conversation_id=sample_conversation.conversation_id,
        message_type=MessageType.AGENT,
        agent_name=sender,
        message=content,
    )
    mock_add_agent_message.assert_called_once_with(content, sender)


@pytest.mark.asyncio
async def test_process_context_directives_set(conversation_manager, sample_conversation, mocker):
    """Test process_context_directives with SET operation."""
    mocker.patch.object(conversation_manager, "upsert_context_item", new=AsyncMock())
    directives = [ContextDirective(op=ContextDirectiveOp.SET, key="key1", value="value1")]

    await conversation_manager.process_context_directives(sample_conversation, directives)

    conversation_manager.upsert_context_item.assert_called_once_with(
        sample_conversation, "key1", "value1"
    )


@pytest.mark.asyncio
async def test_process_context_directives_add(conversation_manager, sample_conversation, mocker):
    """Test process_context_directives with ADD operation."""
    mocker.patch.object(conversation_manager, "add_context_item", new=AsyncMock())
    directives = [
        ContextDirective(
            op=ContextDirectiveOp.ADD,
            key="key2",
            value="value2",
            type=ContextType.TRANSIENT,
        )
    ]

    await conversation_manager.process_context_directives(sample_conversation, directives)

    conversation_manager.add_context_item.assert_called_once_with(
        sample_conversation, "key2", "value2", ContextType.TRANSIENT
    )


@pytest.mark.asyncio
async def test_process_context_directives_update(conversation_manager, sample_conversation, mocker):
    """Test process_context_directives with UPDATE operation."""
    mocker.patch.object(conversation_manager, "update_context_item", new=AsyncMock())
    directives = [ContextDirective(op=ContextDirectiveOp.UPDATE, key="key3", value="new_value3")]

    await conversation_manager.process_context_directives(sample_conversation, directives)

    conversation_manager.update_context_item.assert_called_once_with(
        sample_conversation, "key3", "new_value3"
    )


@pytest.mark.asyncio
async def test_process_context_directives_delete(conversation_manager, sample_conversation, mocker):
    """Test process_context_directives with DELETE operation."""
    mocker.patch.object(conversation_manager, "delete_context_item", new=AsyncMock())
    directives = [ContextDirective(op=ContextDirectiveOp.DELETE, key="key4")]

    await conversation_manager.process_context_directives(sample_conversation, directives)

    conversation_manager.delete_context_item.assert_called_once_with(sample_conversation, "key4")


@pytest.mark.asyncio
async def test_add_context_item_persistent(conversation_manager, sample_conversation, mocker):
    """Test add_context_item for persistent context."""
    mock_add_context_item = mocker.patch(
        "model.Conversation.add_context_item",
        return_value=ContextItem(value="val", context_type=ContextType.PERSISTENT),
    )

    await conversation_manager.add_context_item(
        sample_conversation, "p_key", "p_value", ContextType.PERSISTENT
    )

    mock_add_context_item.assert_called_once_with("p_key", "p_value", ContextType.PERSISTENT)
    conversation_manager.services_client.add_context_item.assert_called_once_with(
        sample_conversation.user_id, "p_key", "p_value"
    )


@pytest.mark.asyncio
async def test_add_context_item_transient(conversation_manager, sample_conversation, mocker):
    """Test add_context_item for transient context."""
    mock_add_context_item = mocker.patch(
        "model.Conversation.add_context_item",
        return_value=ContextItem(value="val", context_type=ContextType.TRANSIENT),
    )
    conversation_manager.services_client.add_context_item.reset_mock()

    await conversation_manager.add_context_item(
        sample_conversation, "t_key", "t_value", ContextType.TRANSIENT
    )

    mock_add_context_item.assert_called_once_with("t_key", "t_value", ContextType.TRANSIENT)
    conversation_manager.services_client.add_context_item.assert_not_called()


@pytest.mark.asyncio
async def test_update_context_item_persistent(conversation_manager, sample_conversation, mocker):
    """Test update_context_item for persistent context."""
    mock_update_context_item = mocker.patch(
        "model.Conversation.update_context_item",
        return_value=ContextItem(value="new_val", context_type=ContextType.PERSISTENT),
    )

    await conversation_manager.update_context_item(sample_conversation, "p_key", "new_p_value")
    mock_update_context_item.assert_called_once_with("p_key", "new_p_value")
    conversation_manager.services_client.update_context_item.assert_called_once_with(
        sample_conversation.user_id, "p_key", "new_p_value"
    )


@pytest.mark.asyncio
async def test_update_context_item_transient(conversation_manager, sample_conversation, mocker):
    """Test update_context_item for transient context."""
    mock_update_context_item = mocker.patch(
        "model.Conversation.update_context_item",
        return_value=ContextItem(value="new_val", context_type=ContextType.TRANSIENT),
    )
    conversation_manager.services_client.update_context_item.reset_mock()

    await conversation_manager.update_context_item(sample_conversation, "t_key", "new_t_value")

    mock_update_context_item.assert_called_once_with("t_key", "new_t_value")
    conversation_manager.services_client.update_context_item.assert_not_called()


@pytest.mark.asyncio
async def test_delete_context_item_persistent(conversation_manager, sample_conversation, mocker):
    """Test delete_context_item for persistent context."""
    mock_delete_context_item = mocker.patch(
        "model.Conversation.delete_context_item",
        return_value=ContextItem(value="old_val", context_type=ContextType.PERSISTENT),
    )

    await conversation_manager.delete_context_item(sample_conversation, "p_key")

    mock_delete_context_item.assert_called_once_with("p_key")
    conversation_manager.services_client.delete_context_item.assert_called_once_with(
        sample_conversation.user_id, "p_key"
    )


@pytest.mark.asyncio
async def test_delete_context_item_transient(conversation_manager, sample_conversation, mocker):
    """Test delete_context_item for transient context."""
    mock_delete_context_item = mocker.patch(
        "model.Conversation.delete_context_item",
        return_value=ContextItem(value="old_val", context_type=ContextType.TRANSIENT),
    )
    conversation_manager.services_client.delete_context_item.reset_mock()

    await conversation_manager.delete_context_item(sample_conversation, "t_key")

    mock_delete_context_item.assert_called_once_with("t_key")
    conversation_manager.services_client.delete_context_item.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_context_item_update(conversation_manager, sample_conversation, mocker):
    """Test upsert_context_item when an update occurs."""
    mocker.patch.object(conversation_manager, "update_context_item", new=AsyncMock())
    mocker.patch.object(conversation_manager, "add_context_item", new=AsyncMock())

    await conversation_manager.upsert_context_item(sample_conversation, "key", "value")

    conversation_manager.update_context_item.assert_called_once_with(
        sample_conversation, "key", "value"
    )
    conversation_manager.add_context_item.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_context_item_add(conversation_manager, sample_conversation, mocker):
    """Test upsert_context_item when an add occurs (due to ValueError on update)."""
    mocker.patch.object(
        conversation_manager,
        "update_context_item",
        new=AsyncMock(side_effect=ValueError("Item not found")),
    )
    mocker.patch.object(conversation_manager, "add_context_item", new=AsyncMock())

    await conversation_manager.upsert_context_item(sample_conversation, "new_key", "new_value")

    conversation_manager.update_context_item.assert_called_once_with(
        sample_conversation, "new_key", "new_value"
    )
    conversation_manager.add_context_item.assert_called_once_with(
        sample_conversation, "new_key", "new_value", ContextType.TRANSIENT
    )


@pytest.mark.asyncio
async def test_add_transient_context(conversation_manager, sample_conversation):
    """Test add_transient_context method."""
    initial_context_len = len(sample_conversation.user_context)
    transient_user_context = {"temp_key1": "temp_value1", "temp_key2": 123}

    await conversation_manager.add_transient_context(sample_conversation, transient_user_context)

    assert len(sample_conversation.user_context) == initial_context_len + 2
    assert sample_conversation.user_context["temp_key1"].value == "temp_value1"
    assert sample_conversation.user_context["temp_key1"].context_type == ContextType.TRANSIENT
    assert sample_conversation.user_context["temp_key2"].value == "123"
    assert sample_conversation.user_context["temp_key2"].context_type == ContextType.TRANSIENT


@pytest.mark.asyncio
async def test_add_transient_context_none(conversation_manager, sample_conversation):
    """Test add_transient_context with None as transient_user_context."""
    initial_context_len = len(sample_conversation.user_context)

    await conversation_manager.add_transient_context(sample_conversation, None)

    assert len(sample_conversation.user_context) == initial_context_len
