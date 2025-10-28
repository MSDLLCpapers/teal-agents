from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import ChatMessageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.streaming_chat_message_content import StreamingChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from sk_agents.configs import TA_PERSISTENCE_CLASS, TA_PERSISTENCE_MODULE
from sk_agents.exceptions import (
    AgentInvokeException,
    AuthenticationException,
    PersistenceCreateError,
    PersistenceLoadError,
)
from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.persistence.task_persistence_manager import TaskPersistenceManager
from sk_agents.ska_types import BaseConfig, ContentType, MultiModalItem, TokenUsage
from sk_agents.tealagents.models import (
    AgentTask,
    AgentTaskItem,
    HitlResponse,
    ResumeRequest,
    TealAgentsPartialResponse,
    TealAgentsResponse,
    UserMessage,
)
from sk_agents.tealagents.v1alpha1.agent.config import Spec
from sk_agents.tealagents.v1alpha1.agent.handler import TealAgentsV1Alpha1Handler
from sk_agents.tealagents.v1alpha1.agent_builder import AgentBuilder
from sk_agents.tealagents.v1alpha1.config import AgentConfig


def _create_mock_agent(mocker, model_type="test_model", chat_service=None):
    """Helper function to create a standardized mock agent."""
    mock_agent = mocker.MagicMock()
    mock_agent.get_model_type.return_value = model_type
    mock_agent.agent.kernel = MagicMock()
    mock_agent.agent.arguments = {}

    if chat_service:
        mock_agent.agent.kernel.select_ai_service.return_value = (chat_service, {})

    return mock_agent


@pytest.fixture
def mock_config():
    """Mocks the Config object."""
    test_agent = AgentConfig(
        name="TestAgent",
        model="gpt-4o",
        system_prompt="test prompt",
        temperature=0.5,
        plugins=None,
    )
    config = BaseConfig(
        apiVersion="tealagents/v1alpha1",
        name="TestAgent",
        version=0.1,
        description="test agent",
        spec=Spec(agent=test_agent),
    )

    return config


@pytest.fixture
def mock_agent_builder():
    """Provides a mock AgentBuilder instance."""
    return MagicMock(spec=AgentBuilder)


@pytest.fixture
def mock_state_manager():
    """Provides a mock TaskPersistenceManager instance."""
    return MagicMock(spec=TaskPersistenceManager)


@pytest.fixture
def mock_app_config():
    """Provides a mock AppConfig instance."""
    mock_config = MagicMock()
    # Configure the mock to return default values for persistence configs
    mock_config.get.side_effect = lambda key: {
        TA_PERSISTENCE_MODULE.env_name: TA_PERSISTENCE_MODULE.default_value,
        TA_PERSISTENCE_CLASS.env_name: TA_PERSISTENCE_CLASS.default_value,
    }.get(key, MagicMock())  # Return MagicMock for other keys

    return mock_config


@pytest.fixture
def teal_agents_handler(mock_config, mock_agent_builder, mock_app_config, mock_state_manager):
    """Provides an initialized TealAgentsV1Alpha1Handler instance."""
    return TealAgentsV1Alpha1Handler(
        config=mock_config,
        app_config=mock_app_config,
        agent_builder=mock_agent_builder,
        state_manager=mock_state_manager,
    )


@pytest.fixture
def user_message():
    return UserMessage(
        session_id="test-session-id",
        task_id="test-task-id",
        items=[MultiModalItem(content_type=ContentType.TEXT, content="test content")],
        user_context={"City": "New York", "Team": "AI Team"},
    )


@pytest.fixture
def mock_date_time():
    return datetime(2025, 1, 1, 10, 0, 0)


@pytest.fixture
def agent_task_item(mock_date_time):
    return AgentTaskItem(
        task_id="task-1",
        role="user",
        item=MultiModalItem(content_type=ContentType.TEXT, content="task-1-content"),
        request_id="task-1-request-id",
        updated=mock_date_time,
    )


@pytest.fixture
def agent_task(mock_date_time, agent_task_item):
    return AgentTask(
        task_id=agent_task_item.task_id,
        session_id="test-session-id",
        user_id="test-user",
        items=[agent_task_item],
        created_at=mock_date_time,
        last_updated=mock_date_time,
        status="Running",
    )


@pytest.fixture
def agent_task_invoke(mock_date_time, agent_task_item, user_message):
    return AgentTask(
        task_id=user_message.task_id,
        session_id=user_message.session_id,
        user_id="test-user",
        items=[agent_task_item],
        created_at=mock_date_time,
        last_updated=mock_date_time,
        status="Running",
    )


@pytest.fixture
def agent_response(agent_task):
    return TealAgentsResponse(
        session_id=agent_task.session_id,
        task_id=agent_task.task_id,
        request_id="test_request_id",
        output="This is the agent's response.",
        token_usage=TokenUsage(completion_tokens=100, prompt_tokens=200, total_tokens=300),
    )


class MockChatCompletionClient(ChatCompletionClientBase):
    ai_model_id: str = "test_model_id"

    async def get_chat_message_contents(self, **kwargs):
        return [
            ChatMessageContent(
                role=AuthorRole.ASSISTANT, items=[TextContent(text="Agent's final response.")]
            )
        ]

    async def get_streaming_chat_message_contents(self, **kwargs):
        yield [
            ChatMessageContent(
                role=AuthorRole.ASSISTANT, items=[TextContent(text="Agent's final response.")]
            )
        ]


def test_augment_user_context(user_message):
    """
    Test that a message is added to chat history when user_context is provided.
    """
    user_input = user_message
    chat_history = ChatHistory()
    expected_content = (
        "The following user context was provided:\n  City: New York\n  Team: AI Team\n"
    )
    TealAgentsV1Alpha1Handler._augment_with_user_context(
        inputs=user_input, chat_history=chat_history
    )
    assert len(chat_history) == 1
    added_message = chat_history[0]

    assert isinstance(added_message, ChatMessageContent)
    assert len(added_message.items) == 1
    assert isinstance(added_message.items[0], TextContent)

    assert chat_history.__dict__["messages"][0].items[0].text == expected_content


def test_configure_agent_task(mocker, user_message):
    """
    Test that _configure_agent_task correctly creates an AgentTask
    with a single TextContent item.
    """
    mock_now = datetime(2025, 1, 1, 10, 0, 0)
    mocker.patch("sk_agents.tealagents.v1alpha1.agent.handler.datetime").now.return_value = mock_now

    session_id = "test-session-id"
    user_id = "test-user-id"
    task_id = "test-task-id"
    role = "user"
    request_id = "test-request-id"
    status = "Running"

    agent_task = TealAgentsV1Alpha1Handler._configure_agent_task(
        session_id=session_id,
        user_id=user_id,
        task_id=task_id,
        role=role,
        request_id=request_id,
        inputs=user_message,
        status=status,
    )

    assert isinstance(agent_task, AgentTask)
    assert agent_task.task_id == task_id
    assert agent_task.session_id == session_id
    assert agent_task.user_id == user_id
    assert agent_task.status == status
    assert agent_task.created_at == mock_now
    assert agent_task.last_updated == mock_now

    assert len(agent_task.items) == 1
    agent_task_item = agent_task.items[0]
    assert isinstance(agent_task_item, AgentTaskItem)
    assert agent_task_item.task_id == task_id
    assert agent_task_item.role == role
    assert agent_task_item.request_id == request_id
    assert agent_task_item.updated == mock_now

    assert agent_task_item.item.content == user_message.items[0].content


@pytest.mark.parametrize(
    "token,side_effect,expected_result,should_raise",
    [
        ("valid_auth_token_123", None, "authenticated_user_id", False),
        ("invalid_auth_token_xyz", Exception("Token is expired"), None, True),
    ],
)
@pytest.mark.asyncio
async def test_authenticate_user(
    teal_agents_handler, mocker, token, side_effect, expected_result, should_raise
):
    """
    Test authenticate_user for both success and failure scenarios.
    """
    if side_effect:
        mocker.patch.object(
            teal_agents_handler.authorizer, "authorize_request", side_effect=side_effect
        )
    else:
        mocker.patch.object(
            teal_agents_handler.authorizer, "authorize_request", return_value=expected_result
        )

    if should_raise:
        with pytest.raises(AuthenticationException):
            await teal_agents_handler.authenticate_user(token=token)
    else:
        user_id = await teal_agents_handler.authenticate_user(token=token)
        assert user_id == expected_result
        teal_agents_handler.authorizer.authorize_request.assert_called_once_with(auth_header=token)


def test_handle_state_id(user_message):
    """Test the _handle_state_id static method for various input scenarios."""

    # Scenario 1: Both session_id and task_id are provided
    session_id_1, task_id_1, request_id_1 = TealAgentsV1Alpha1Handler.handle_state_id(user_message)
    assert session_id_1 == user_message.session_id
    assert task_id_1 == user_message.task_id
    assert request_id_1

    # Scenario 2: session_id provided, task_id is None
    input_2 = user_message
    input_2.task_id = None
    session_id_2, task_id_2, request_id_2 = TealAgentsV1Alpha1Handler.handle_state_id(input_2)
    assert session_id_2 == input_2.session_id
    assert task_id_2
    assert request_id_2

    # Scenario 3: Neither session_id nor task_id are provided
    input_3 = user_message
    input_3.session_id = None
    input_3.task_id = None
    session_id_3, task_id_3, request_id_3 = TealAgentsV1Alpha1Handler.handle_state_id(input_3)
    assert session_id_3
    assert task_id_3
    assert request_id_3


@pytest.mark.asyncio
async def test_manage_incoming_task_load_success(
    teal_agents_handler, mocker, user_message, agent_task
):
    """
    Test _manage_incoming_task when the task is successfully loaded from state.
    """
    task_id = user_message.task_id
    session_id = user_message.session_id
    user_id = "test_user"
    request_id = "test_request_id"

    mocker.patch.object(teal_agents_handler.state, "load", return_value=agent_task)
    mocker.patch.object(teal_agents_handler.state, "create")

    await teal_agents_handler._manage_incoming_task(
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        inputs=user_message,
    )

    teal_agents_handler.state.load.assert_called_once_with(task_id)
    teal_agents_handler.state.create.assert_not_called()


@pytest.mark.parametrize(
    "user_id,task_user_id,should_raise",
    [("test_user", "test_user", False), ("test_user", "mismatch_user_id", True)],
)
def test_validate_user_id(user_message, user_id, task_user_id, should_raise):
    """
    Test _validate_user_id with matching and mismatching user IDs.
    """
    task_id = user_message.task_id
    agent_task = AgentTask(
        task_id=task_id,
        session_id="test_session",
        user_id=task_user_id,
        items=[],
        created_at=datetime.now(),
        last_updated=datetime.now(),
        status="Running",
    )

    if should_raise:
        with pytest.raises(AgentInvokeException):
            TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)
    else:
        try:
            TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)
        except AgentInvokeException:
            pytest.fail("AgentInvokeException was raised unexpectedly.")


@pytest.mark.asyncio
async def test_manage_agent_response_task(
    teal_agents_handler, mocker, mock_date_time, agent_task, agent_task_item, agent_response
):
    """
    Test that _manage_agent_response_task correctly appends a new item
    and updates the agent task in state.
    """
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.datetime"
    ).now.return_value = mock_date_time

    mocker.patch.object(teal_agents_handler.state, "update", new_callable=mocker.AsyncMock)

    await teal_agents_handler._manage_agent_response_task(agent_task, agent_response)

    assert len(agent_task.items) == 2
    new_item = agent_task.items[1]

    assert isinstance(new_item, AgentTaskItem)
    assert new_item.task_id == agent_response.task_id
    assert new_item.role == "assistant"
    assert isinstance(new_item.item, MultiModalItem)
    assert new_item.item.content_type == ContentType.TEXT
    assert new_item.item.content == agent_response.output
    assert new_item.request_id == agent_response.request_id
    assert new_item.updated == mock_date_time

    assert agent_task.last_updated == mock_date_time
    teal_agents_handler.state.update.assert_called_once_with(agent_task)


@pytest.mark.asyncio
async def test_invoke_success(
    teal_agents_handler, mocker, mock_config, user_message, agent_task_invoke, agent_response
):
    """
    Test the successful invocation of the agent.
    Mocks all internal and external dependencies.
    """

    auth_token = "test_auth_token"
    mock_user_id = "tes_user_id"
    mock_session_id = user_message.session_id
    mock_task_id = user_message.task_id
    mock_request_id = "test_request_id"

    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value=mock_user_id)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.TealAgentsV1Alpha1Handler.handle_state_id",
        return_value=(mock_session_id, mock_task_id, mock_request_id),
    )
    mocker.patch.object(
        teal_agents_handler, "_manage_incoming_task", return_value=agent_task_invoke
    )
    mocker.patch.object(
        teal_agents_handler.state,
        "load_by_request_id",
        return_value=agent_task_invoke,
        new_callable=mocker.AsyncMock,
    )
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.TealAgentsV1Alpha1Handler._validate_user_id"
    )
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.TealAgentsV1Alpha1Handler._augment_with_user_context"
    )
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.TealAgentsV1Alpha1Handler._build_chat_history"
    )
    mocker.patch.object(
        teal_agents_handler, "_manage_agent_response_task", new_callable=mocker.AsyncMock
    )

    mock_agent = mocker.MagicMock()
    mock_agent.get_model_type.return_value = "test_model_type"

    mock_chat_completion_service = MockChatCompletionClient()
    mock_settings = {}
    mock_agent = mocker.MagicMock()
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )
    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)

    # Create an async generator for agent.invoke
    async def mock_agent_invoke_generator():
        yield ChatMessageContent(
            role=AuthorRole.ASSISTANT, items=[TextContent(text="Agent's final response.")]
        )

    mock_agent.invoke.return_value = mock_agent_invoke_generator()

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=50, prompt_tokens=100, total_tokens=150),
    )

    result = await teal_agents_handler.invoke(auth_token=auth_token, inputs=user_message)

    teal_agents_handler.authenticate_user.assert_called_once_with(token=auth_token)
    TealAgentsV1Alpha1Handler.handle_state_id.assert_called_once_with(user_message)
    teal_agents_handler._manage_incoming_task.assert_called_once_with(
        mock_task_id, mock_session_id, mock_user_id, mock_request_id, user_message
    )
    TealAgentsV1Alpha1Handler._validate_user_id.assert_called_once_with(
        mock_user_id, mock_task_id, agent_task_invoke
    )
    teal_agents_handler.agent_builder.build_agent.assert_called_once()
    TealAgentsV1Alpha1Handler._augment_with_user_context.assert_called_once()
    TealAgentsV1Alpha1Handler._build_chat_history.assert_called_once()
    teal_agents_handler._manage_agent_response_task.assert_awaited_once()

    assert isinstance(result, TealAgentsResponse)
    assert result.session_id == mock_session_id
    assert result.task_id == mock_task_id
    assert result.request_id == mock_request_id
    assert result.output == "Agent's final response."
    assert result.source == f"{teal_agents_handler.name}:{teal_agents_handler.version}"
    assert result.token_usage.completion_tokens == 50
    assert result.token_usage.prompt_tokens == 100
    assert result.token_usage.total_tokens == 150


@pytest.mark.asyncio
async def test_invoke_intervention_required(
    teal_agents_handler, mocker, user_message, agent_task_invoke
):
    """
    Test the invocation of the agent when intervention is required.
    Mocks all internal and external dependencies.
    """

    auth_token = "test_auth_token"
    mock_user_id = "test_user_id"
    mock_session_id = user_message.session_id
    mock_task_id = user_message.task_id
    mock_request_id = "test_request_id"

    # Mock dependencies
    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value=mock_user_id)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.TealAgentsV1Alpha1Handler.handle_state_id",
        return_value=(mock_session_id, mock_task_id, mock_request_id),
    )
    mocker.patch.object(
        teal_agents_handler, "_manage_incoming_task", return_value=agent_task_invoke
    )
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.TealAgentsV1Alpha1Handler._validate_user_id"
    )
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.TealAgentsV1Alpha1Handler._augment_with_user_context"
    )
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.TealAgentsV1Alpha1Handler._build_chat_history"
    )
    mocker.patch.object(
        teal_agents_handler.state,
        "load_by_request_id",
        return_value=agent_task_invoke,
        new_callable=mocker.AsyncMock,
    )

    # Mock intervention check to always return True
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.hitl_manager.check_for_intervention",
        return_value=True,
    )

    # Mock token usage
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=0, prompt_tokens=0, total_tokens=0),
    )

    # Mock ChatCompletion service yielding a FunctionCallContent
    class MockChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model_id"  # Define the required field

        async def get_chat_message_contents(self, *args, **kwargs):
            fc = FunctionCallContent(
                plugin_name="test_plugin",
                function_name="test_function",
                arguments={"arg": "value"},
            )
            msg = ChatMessageContent(role=AuthorRole.ASSISTANT, items=[fc])
            return [msg]

    # Mock kernel to return the mocked service
    mock_chat_completion_service = MockChatCompletionService()
    mock_settings = {}
    mock_agent = mocker.MagicMock()
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )
    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)

    # Mock state.create to ensure the task is added to the in-memory storage
    mocker.patch.object(teal_agents_handler.state, "create", new_callable=mocker.AsyncMock)
    mocker.patch.object(teal_agents_handler.state, "update", new_callable=mocker.AsyncMock)

    # Add the task to the in-memory storage
    await teal_agents_handler.state.create(agent_task_invoke)

    # Invoke the handler
    result = await teal_agents_handler.invoke(auth_token=auth_token, inputs=user_message)

    assert isinstance(result, HitlResponse)
    assert result.task_id == "test-task-id"
    assert result.session_id == "test-session-id"
    assert result.request_id == "test_request_id"
    assert len(result.tool_calls) == 1
    assert "approve" in result.approval_url
    assert "reject" in result.rejection_url


def test_invalid_config_raises_value_error(mock_agent_builder, mock_app_config, mock_state_manager):
    """
    Test that TealAgentsV1Alpha1Handler raises ValueError when config doesn't have 'spec' attribute.
    """

    # Create a mock config that doesn't have the 'spec' attribute
    class InvalidConfig:
        def __init__(self):
            self.version = 0.1
            self.name = "TestAgent"
            # Note: no 'spec' attribute

    invalid_config = InvalidConfig()

    with pytest.raises(ValueError, match="Invalid config"):
        TealAgentsV1Alpha1Handler(
            config=invalid_config,
            app_config=mock_app_config,
            agent_builder=mock_agent_builder,
            state_manager=mock_state_manager,
        )


@pytest.mark.asyncio
async def test_invoke_function_static_method(mocker):
    """
    Test the static _invoke_function method.
    """
    # Create mock function call content
    mock_fc_content = MagicMock(spec=FunctionCallContent)
    mock_fc_content.plugin_name = "test_plugin"
    mock_fc_content.function_name = "test_function"
    mock_fc_content.to_kernel_arguments.return_value = {"arg1": "value1"}

    # Create mock kernel and function
    mock_kernel = MagicMock()
    mock_function = MagicMock()
    mock_kernel.get_function.return_value = mock_function

    # Mock function result - make it async
    mock_function_result = MagicMock()
    mock_function.invoke = mocker.AsyncMock(return_value=mock_function_result)

    # Mock FunctionResultContent.from_function_call_content_and_result
    mock_result_content = MagicMock()
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.FunctionResultContent.from_function_call_content_and_result",
        return_value=mock_result_content,
    )

    # Call the method
    result = await TealAgentsV1Alpha1Handler._invoke_function(mock_kernel, mock_fc_content)

    # Verify the interactions
    mock_kernel.get_function.assert_called_once_with("test_plugin", "test_function")
    mock_fc_content.to_kernel_arguments.assert_called_once()
    mock_function.invoke.assert_called_once_with(mock_kernel, {"arg1": "value1"})
    assert result == mock_result_content


@pytest.mark.parametrize(
    "action,expected_content",
    [("rejected", "tool execution rejected"), ("approved", "tool execution approved")],
)
def test_task_item_creation(action, expected_content):
    """
    Test the static task item creation methods for both rejected and approved actions.
    """
    task_id = "test-task-id"
    request_id = "test-request-id"

    if action == "rejected":
        result = TealAgentsV1Alpha1Handler._rejected_task_item(task_id, request_id)
    else:
        result = TealAgentsV1Alpha1Handler._approved_task_item(task_id, request_id)

    assert isinstance(result, AgentTaskItem)
    assert result.task_id == task_id
    assert result.request_id == request_id
    assert result.role == "user"
    assert result.item.content == expected_content
    assert result.item.content_type == ContentType.TEXT


@pytest.mark.asyncio
async def test_manage_incoming_task_exception_handling(teal_agents_handler, mocker, user_message):
    """
    Test that _manage_incoming_task handles exceptions properly.
    """
    task_id = "test-task-id"
    session_id = "test-session-id"
    user_id = "test-user"
    request_id = "test-request-id"

    # Mock the state.load to raise an exception
    mocker.patch.object(
        teal_agents_handler.state, "load", side_effect=RuntimeError("Database error")
    )

    with pytest.raises(
        AgentInvokeException, match="Unexpected error occurred while managing incoming task"
    ):
        await teal_agents_handler._manage_incoming_task(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            inputs=user_message,
        )


@pytest.mark.asyncio
async def test_manage_incoming_task_persistence_errors(teal_agents_handler, mocker, user_message):
    """
    Test that _manage_incoming_task handles PersistenceLoadError and
    PersistenceCreateError properly.
    """
    task_id = "test-task-id"
    session_id = "test-session-id"
    user_id = "test-user"
    request_id = "test-request-id"

    # Test PersistenceLoadError
    mocker.patch.object(
        teal_agents_handler.state,
        "load",
        side_effect=PersistenceLoadError("Failed to load task"),
    )

    with pytest.raises(
        AgentInvokeException, match=r"Failed to load or create task.*Failed to load task"
    ):
        await teal_agents_handler._manage_incoming_task(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            inputs=user_message,
        )

    # Test PersistenceCreateError
    mocker.patch.object(teal_agents_handler.state, "load", return_value=None)
    mocker.patch.object(
        teal_agents_handler.state,
        "create",
        side_effect=PersistenceCreateError("Failed to create task"),
    )

    with pytest.raises(
        AgentInvokeException, match=r"Failed to load or create task.*Failed to create task"
    ):
        await teal_agents_handler._manage_incoming_task(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            request_id=request_id,
            inputs=user_message,
        )


@pytest.mark.asyncio
async def test_manage_incoming_task_existing_task(
    teal_agents_handler, mocker, user_message, agent_task
):
    """
    Test _manage_incoming_task when an existing task is found.
    This covers the return path when agent_task exists.
    """
    task_id = user_message.task_id
    session_id = user_message.session_id
    user_id = "test_user"
    request_id = "test_request_id"

    # Mock state.load to return an existing task
    mocker.patch.object(teal_agents_handler.state, "load", return_value=agent_task)
    mocker.patch.object(teal_agents_handler.state, "create")

    result = await teal_agents_handler._manage_incoming_task(
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        inputs=user_message,
    )

    # Should return None when task exists (since the existing task is not returned)
    assert result is None
    teal_agents_handler.state.load.assert_called_once_with(task_id)
    teal_agents_handler.state.create.assert_not_called()


@pytest.mark.parametrize(
    "test_case,task_setup,expected_error",
    [
        (
            "not_found",
            lambda teal_agents_handler, mocker: mocker.patch.object(
                teal_agents_handler.state, "load_by_request_id", return_value=None
            ),
            "No agent task found for request ID",
        ),
        (
            "no_chat_history",
            lambda teal_agents_handler, mocker, agent_task=None: (
                setattr(agent_task.items[-1], "chat_history", None),
                mocker.patch.object(
                    teal_agents_handler.state, "load_by_request_id", return_value=agent_task
                ),
            ),
            "Cannot resume task.*chat history not preserved",
        ),
        (
            "not_paused",
            lambda teal_agents_handler, mocker, agent_task=None: (
                setattr(agent_task, "status", "Running"),
                setattr(agent_task.items[-1], "chat_history", ChatHistory()),
                mocker.patch.object(
                    teal_agents_handler.state, "load_by_request_id", return_value=agent_task
                ),
            ),
            "Cannot resume task.*task is in 'Running' state",
        ),
        (
            "empty_items",
            lambda teal_agents_handler, mocker, agent_task=None: (
                setattr(agent_task, "status", "Paused"),
                setattr(agent_task, "items", []),
                mocker.patch.object(
                    teal_agents_handler.state, "load_by_request_id", return_value=agent_task
                ),
            ),
            "Cannot resume task.*task has no items",
        ),
        (
            "insufficient_items",
            lambda teal_agents_handler, mocker, agent_task=None: (
                setattr(agent_task, "status", "Paused"),
                setattr(agent_task.items[0], "chat_history", ChatHistory()),
                setattr(agent_task, "items", [agent_task.items[0]]),
                mocker.patch.object(
                    teal_agents_handler.state, "load_by_request_id", return_value=agent_task
                ),
                # Mock update to simulate corruption that removes items
                mocker.patch.object(
                    teal_agents_handler.state,
                    "update",
                    side_effect=lambda task: setattr(task, "items", []),
                ),
            ),
            "Invalid task state for request ID.*expected at least 2 task items",
        ),
    ],
)
@pytest.mark.asyncio
async def test_resume_task_error_cases(
    teal_agents_handler, mocker, test_case, task_setup, expected_error, agent_task
):
    """
    Test resume_task error cases using parametrized tests.
    """
    auth_token = "test_token"
    request_id = "test_request_id"
    action_status = ResumeRequest(action="approve")

    # Set up authentication mock
    user_id = "test_user" if test_case == "not_found" else agent_task.user_id
    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value=user_id)

    # Apply specific test setup
    if test_case == "not_found":
        task_setup(teal_agents_handler, mocker)
    else:
        task_setup(teal_agents_handler, mocker, agent_task)

    # Test the error condition
    with pytest.raises(AgentInvokeException, match=expected_error):
        await teal_agents_handler.resume_task(auth_token, request_id, action_status, False)


@pytest.mark.asyncio
async def test_resume_task_rejection(teal_agents_handler, mocker, agent_task):
    """
    Test resume_task when action is reject.
    """
    auth_token = "test_token"
    request_id = "test_request_id"
    action_status = ResumeRequest(action="reject")

    # Set up agent task
    agent_task.status = "Paused"
    agent_task.items[-1].chat_history = ChatHistory()

    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value=agent_task.user_id)
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)
    mocker.patch.object(teal_agents_handler.state, "update", new_callable=mocker.AsyncMock)

    result = await teal_agents_handler.resume_task(auth_token, request_id, action_status, False)

    # Verify the result is a RejectedToolResponse
    assert hasattr(result, "task_id")
    assert hasattr(result, "session_id")
    assert hasattr(result, "request_id")

    # Verify agent task was updated
    assert agent_task.status == "Canceled"
    teal_agents_handler.state.update.assert_called_once_with(agent_task)


@pytest.mark.parametrize(
    "error_type,mock_setup,expected_error",
    [
        (
            "no_agent_task",
            lambda teal_agents_handler, mocker: mocker.patch.object(
                teal_agents_handler.state, "load_by_request_id", return_value=None
            ),
            "Agent task with ID test_task_id not found in state",
        ),
        (
            "build_agent_exception",
            lambda teal_agents_handler, mocker, agent_task: (
                mocker.patch.object(
                    teal_agents_handler.state, "load_by_request_id", return_value=agent_task
                ),
                mocker.patch.object(
                    teal_agents_handler.agent_builder,
                    "build_agent",
                    side_effect=RuntimeError("Agent build failed"),
                ),
            ),
            "Agent build failed",
        ),
    ],
)
@pytest.mark.asyncio
async def test_recursion_invoke_error_cases(
    teal_agents_handler, mocker, error_type, mock_setup, expected_error, agent_task
):
    """
    Test recursion_invoke error cases using parametrized tests.
    """
    chat_history = ChatHistory()
    session_id = "test_session_id"
    task_id = "test_task_id"
    request_id = "test_request_id"

    # Apply specific mock setup
    if error_type == "no_agent_task":
        mock_setup(teal_agents_handler, mocker)
    else:
        mock_setup(teal_agents_handler, mocker, agent_task)

    # Test the error condition
    if error_type == "no_agent_task":
        with pytest.raises(PersistenceLoadError, match=expected_error):
            await teal_agents_handler.recursion_invoke(
                chat_history, session_id, task_id, request_id
            )
    else:
        with pytest.raises(RuntimeError, match=expected_error):
            await teal_agents_handler.recursion_invoke(
                chat_history, session_id, task_id, request_id
            )


@pytest.mark.asyncio
async def test_recursion_invoke_exception_in_try_block(teal_agents_handler, mocker, agent_task):
    """
    Test recursion_invoke when an exception occurs inside the try block.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request_id"

    # Mock dependencies
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    mock_agent = MagicMock()
    mock_agent.get_model_type.return_value = "test_model_type"
    mock_agent.agent.kernel = MagicMock()
    mock_agent.agent.arguments = {}

    # Make the kernel.select_ai_service fail
    mock_agent.agent.kernel.select_ai_service.side_effect = RuntimeError("Kernel error")

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)

    with pytest.raises(AgentInvokeException, match="Error invoking TestAgent:0.1for Session ID"):
        await teal_agents_handler.recursion_invoke(chat_history, session_id, task_id, request_id)


@pytest.mark.asyncio
async def test_resume_task_no_pending_tool_calls(teal_agents_handler, mocker, agent_task):
    """
    Test resume_task when pending_tool_calls is None.
    """
    auth_token = "test_token"
    request_id = "test_request_id"
    action_status = ResumeRequest(action="approve")

    # Set up agent task with approval
    agent_task.status = "Paused"
    agent_task.items[-1].chat_history = ChatHistory()
    agent_task.items[-1].pending_tool_calls = None  # No pending tool calls

    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value=agent_task.user_id)
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)
    mocker.patch.object(teal_agents_handler.state, "update", new_callable=mocker.AsyncMock)

    with pytest.raises(AgentInvokeException, match="Pending tool calls not found"):
        await teal_agents_handler.resume_task(auth_token, request_id, action_status, False)


@pytest.mark.asyncio
async def test_resume_task_approval_stream(teal_agents_handler, mocker, agent_task):
    """
    Test resume_task with approval and streaming enabled.
    """
    auth_token = "test_token"
    request_id = "test_request_id"
    action_status = ResumeRequest(action="approve")

    # Set up agent task
    agent_task.status = "Paused"
    agent_task.items[-1].chat_history = ChatHistory()
    # Mock pending tool calls
    agent_task.items[-1].pending_tool_calls = [
        {"plugin_name": "test_plugin", "function_name": "test_function", "arguments": {}}
    ]

    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value=agent_task.user_id)
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)
    mocker.patch.object(teal_agents_handler.state, "update", new_callable=mocker.AsyncMock)

    # Mock the recursive call
    async def mock_stream():
        yield TealAgentsResponse(
            session_id=agent_task.session_id,
            task_id=agent_task.task_id,
            request_id=request_id,
            output="test response",
            source="test",
            token_usage=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
        )

    mocker.patch.object(teal_agents_handler, "recursion_invoke_stream", return_value=mock_stream())

    # Mock agent building and function execution
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)

    # Create a proper function result mock
    mock_function_result = MagicMock()
    mock_function_result.to_chat_message_content.return_value = ChatMessageContent(
        role=AuthorRole.ASSISTANT, content="Function executed successfully"
    )
    mocker.patch.object(
        TealAgentsV1Alpha1Handler, "_invoke_function", return_value=mock_function_result
    )

    result = await teal_agents_handler.resume_task(auth_token, request_id, action_status, True)

    # Should return an async generator
    assert hasattr(result, "__aiter__")


@pytest.mark.asyncio
async def test_manage_incoming_task_create_success(teal_agents_handler, mocker):
    """
    Test _manage_incoming_task when creating a new task.
    """
    session_id = "test-session"
    user_id = "test-user"
    task_id = "test-task"
    request_id = "test-request"
    inputs = UserMessage(
        items=[MultiModalItem(content_type=ContentType.TEXT, content="Test message")],
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        task_id=task_id,
    )

    # Mock state operations
    mocker.patch.object(teal_agents_handler.state, "load", return_value=None)
    mocker.patch.object(teal_agents_handler.state, "create", new_callable=mocker.AsyncMock)

    result = await teal_agents_handler._manage_incoming_task(
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        inputs=inputs,
    )

    assert result.task_id == task_id
    assert result.session_id == session_id
    assert result.user_id == user_id
    assert result.status == "Running"  # Set internally by _configure_agent_task
    teal_agents_handler.state.create.assert_called_once()


def test_build_chat_history_multiple_items():
    """
    Test _build_chat_history with multiple task items.
    """
    # Create agent task with multiple items
    task_items = [
        AgentTaskItem(
            task_id="test-task",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Hello"),
            request_id="req1",
            updated=datetime.now(),
        ),
        AgentTaskItem(
            task_id="test-task",
            role="assistant",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Hi there"),
            request_id="req2",
            updated=datetime.now(),
        ),
    ]

    agent_task = AgentTask(
        task_id="test-task",
        session_id="test-session",
        user_id="test-user",
        items=task_items,
        created_at=datetime.now(),
        last_updated=datetime.now(),
        status="Running",
    )

    chat_history = ChatHistory()
    result = TealAgentsV1Alpha1Handler._build_chat_history(agent_task, chat_history)

    assert len(result) == 2
    assert result[0].role == AuthorRole.USER
    assert result[1].role == AuthorRole.ASSISTANT


@pytest.mark.asyncio
async def test_process_multiple_function_calls(mocker):
    """
    Test processing multiple non-intervention function calls.
    """
    # Create multiple function calls that are NOT interventions
    function_calls = [
        FunctionCallContent(
            name="test_function_1", plugin_name="test_plugin", arguments={"arg1": "value1"}
        ),
        FunctionCallContent(
            name="test_function_2", plugin_name="test_plugin", arguments={"arg2": "value2"}
        ),
    ]

    chat_history = ChatHistory()
    kernel = MagicMock()

    # Mock the function results
    mock_result_1 = MagicMock()
    mock_result_1.to_chat_message_content.return_value = ChatMessageContent(
        role=AuthorRole.ASSISTANT, content="Result 1"
    )
    mock_result_2 = MagicMock()
    mock_result_2.to_chat_message_content.return_value = ChatMessageContent(
        role=AuthorRole.ASSISTANT, content="Result 2"
    )

    # Mock _invoke_function to return our results
    mock_invoke_function = mocker.patch.object(
        TealAgentsV1Alpha1Handler, "_invoke_function", side_effect=[mock_result_1, mock_result_2]
    )

    # Mock hitl_manager.check_for_intervention to return False for both
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.hitl_manager.check_for_intervention",
        return_value=False,
    )

    # Call the method that processes function calls
    await TealAgentsV1Alpha1Handler._manage_function_calls(function_calls, chat_history, kernel)

    # Verify both function calls were processed
    assert mock_invoke_function.call_count == 2
    # Verify results were added to chat history
    assert len(chat_history.messages) == 2


@pytest.mark.asyncio
async def test_response_list_processing(teal_agents_handler, agent_task):
    """
    Test processing when response is a list vs single response.
    """
    # Test with list response
    list_response = ["Hello ", "world!"]

    extra_data_collector = ExtraDataCollector()

    result = await teal_agents_handler.prepare_agent_response(
        agent_task=agent_task,
        request_id="test-request",
        response=list_response,
        token_usage=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
        extra_data_collector=extra_data_collector,
    )

    assert result.output == "Hello world!"
    assert result.token_usage.total_tokens == 30


@pytest.mark.asyncio
async def test_resume_task_non_streaming(teal_agents_handler, mocker, agent_task):
    """
    Test resume_task with stream=False.
    """
    auth_token = "test_token"
    request_id = "test_request_id"
    action_status = ResumeRequest(action="approve")

    # Set up agent task
    agent_task.status = "Paused"
    agent_task.items[-1].chat_history = ChatHistory()
    # Mock pending tool calls
    agent_task.items[-1].pending_tool_calls = [
        {"plugin_name": "test_plugin", "function_name": "test_function", "arguments": {}}
    ]

    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value=agent_task.user_id)
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)
    mocker.patch.object(teal_agents_handler.state, "update", new_callable=mocker.AsyncMock)

    # Mock the recursive call
    mock_response = TealAgentsResponse(
        session_id=agent_task.session_id,
        task_id=agent_task.task_id,
        request_id=request_id,
        output="test response",
        source="test",
        token_usage=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    mocker.patch.object(teal_agents_handler, "recursion_invoke", return_value=mock_response)

    # Mock agent building and function execution
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)

    # Create a proper function result mock
    mock_function_result = MagicMock()
    mock_function_result.to_chat_message_content.return_value = ChatMessageContent(
        role=AuthorRole.ASSISTANT, content="Function executed successfully"
    )
    mocker.patch.object(
        TealAgentsV1Alpha1Handler, "_invoke_function", return_value=mock_function_result
    )

    # Call with stream=False
    result = await teal_agents_handler.resume_task(auth_token, request_id, action_status, False)

    # Should return the direct response, not an async generator
    assert isinstance(result, TealAgentsResponse)
    assert result.output == "test response"
    assert result.task_id == agent_task.task_id


@pytest.mark.parametrize("method_name", ["invoke", "invoke_stream"])
@pytest.mark.asyncio
async def test_invoke_agent_task_none_exception(
    teal_agents_handler, mocker, user_message, method_name
):
    """
    Test invoke/invoke_stream methods when agent_task is None.
    """
    auth_token = "test_token"

    # Mock authentication
    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value="test_user")

    # Mock _manage_incoming_task to return None
    mocker.patch.object(teal_agents_handler, "_manage_incoming_task", return_value=None)

    # Should raise AgentInvokeException
    with pytest.raises(AgentInvokeException, match="Agent task not created"):
        method = getattr(teal_agents_handler, method_name)
        await method(auth_token, user_message)


@pytest.mark.asyncio
async def test_invoke_stream_method(teal_agents_handler, mocker, user_message, agent_task):
    """
    Test the complete invoke_stream method.
    """
    auth_token = "test_token"

    # Mock authentication
    mocker.patch.object(teal_agents_handler, "authenticate_user", return_value=agent_task.user_id)

    # Mock _manage_incoming_task to return agent_task
    mocker.patch.object(teal_agents_handler, "_manage_incoming_task", return_value=agent_task)

    # Mock the streaming response
    async def mock_stream():
        yield TealAgentsResponse(
            session_id=agent_task.session_id,
            task_id=agent_task.task_id,
            request_id="test_request",
            output="streaming response",
            source="test",
            token_usage=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
        )

    mocker.patch.object(teal_agents_handler, "recursion_invoke_stream", return_value=mock_stream())

    # Call invoke_stream
    result_stream = await teal_agents_handler.invoke_stream(auth_token, user_message)

    # Should return an async iterable
    assert hasattr(result_stream, "__aiter__")

    # Collect results
    results = []
    async for item in result_stream:
        results.append(item)

    assert len(results) == 1
    assert results[0].output == "streaming response"


@pytest.mark.asyncio
async def test_recursion_invoke_final_response_none(teal_agents_handler, mocker, agent_task):
    """
    Test recursion_invoke when final_response is None.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request"

    # Mock state loading
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    # Mock agent building
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mock_agent.get_model_type.return_value = "test_model"

    # Create a custom mock for chat completion service that returns empty response
    class TestChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model"

        async def get_chat_message_contents(self, **kwargs):
            # Return empty list - simulates no response received from LLM
            return []

    mock_chat_completion_service = TestChatCompletionService()
    mock_settings = {}
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=0, prompt_tokens=10, total_tokens=10),
    )

    # Should raise AgentInvokeException
    with pytest.raises(AgentInvokeException, match="No response received from LLM"):
        await teal_agents_handler.recursion_invoke(
            inputs=chat_history, session_id=session_id, task_id=task_id, request_id=request_id
        )


@pytest.mark.asyncio
async def test_recursion_invoke_stream_method(teal_agents_handler, mocker, agent_task):
    """
    Test the complete recursion_invoke_stream method.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request"

    # Mock state loading
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    # Mock agent building
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mock_agent.get_model_type.return_value = "test_model"

    # Create streaming chat message content
    streaming_content = StreamingChatMessageContent(
        role=AuthorRole.ASSISTANT, content="This is a streaming response", choice_index=0
    )

    # Create a custom mock for chat completion service
    class TestChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model"

        async def get_chat_message_contents(self, **kwargs):
            # Return streaming response
            return [streaming_content]

    mock_chat_completion_service = TestChatCompletionService()
    mock_settings = {}
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    # Mock prepare_agent_response
    mock_response = TealAgentsResponse(
        session_id=session_id,
        task_id=task_id,
        request_id=request_id,
        output="Final streaming response",
        source="test",
        token_usage=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    mocker.patch.object(teal_agents_handler, "prepare_agent_response", return_value=mock_response)

    # Call the streaming method
    result_stream = teal_agents_handler.recursion_invoke_stream(
        chat_history, session_id, task_id, request_id
    )

    # Collect results
    results = []
    async for item in result_stream:
        results.append(item)

    # Should have at least the final response
    assert len(results) >= 1
    final_result = results[-1]
    assert final_result.output == "Final streaming response"


@pytest.mark.asyncio
async def test_recursion_invoke_stream_no_agent_task(teal_agents_handler, mocker):
    """
    Test recursion_invoke_stream when agent_task is not found.
    """
    chat_history = ChatHistory()
    session_id = "test-session"
    task_id = "test-task"
    request_id = "test_request"

    # Mock state loading to return None
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=None)

    # Should raise PersistenceLoadError
    with pytest.raises(PersistenceLoadError, match="Agent task with ID test-task not found"):
        async for _ in teal_agents_handler.recursion_invoke_stream(
            chat_history, session_id, task_id, request_id
        ):
            pass


@pytest.mark.asyncio
async def test_recursion_invoke_stream_no_responses(teal_agents_handler, mocker, agent_task):
    """
    Test recursion_invoke_stream when no responses are returned.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request"

    # Mock state loading
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    # Mock agent building
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mock_agent.get_model_type.return_value = "test_model"

    # Create a custom mock for chat completion service that returns empty response
    class TestChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model"

        async def get_chat_message_contents(self, **kwargs):
            # Return empty list - no responses
            return []

    mock_chat_completion_service = TestChatCompletionService()
    mock_settings = {}
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)

    # Call the streaming method
    result_stream = teal_agents_handler.recursion_invoke_stream(
        chat_history, session_id, task_id, request_id
    )

    # Should return early with no results
    results = []
    async for item in result_stream:
        results.append(item)

    # Should have no results due to early return
    assert len(results) == 0


@pytest.mark.asyncio
async def test_recursion_invoke_stream_with_partial_response(
    teal_agents_handler, mocker, agent_task
):
    """
    Test recursion_invoke_stream with partial response yielding.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request"

    # Mock state loading
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    # Mock agent building
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mock_agent.get_model_type.return_value = "test_model"

    # Create streaming content with partial response
    streaming_content = StreamingChatMessageContent(
        role=AuthorRole.ASSISTANT, content="Partial streaming content", choice_index=0
    )

    # Create a custom mock for chat completion service
    class TestChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model"

        async def get_chat_message_contents(self, **kwargs):
            # Return streaming response with content that will be yielded as partial
            return [streaming_content]

    mock_chat_completion_service = TestChatCompletionService()
    mock_settings = {}
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    # Mock prepare_agent_response
    mock_response = TealAgentsResponse(
        session_id=session_id,
        task_id=task_id,
        request_id=request_id,
        output="Final response after partial",
        source="test",
        token_usage=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    mocker.patch.object(teal_agents_handler, "prepare_agent_response", return_value=mock_response)

    # Call the streaming method
    result_stream = teal_agents_handler.recursion_invoke_stream(
        chat_history, session_id, task_id, request_id
    )

    # Collect results
    results = []
    async for item in result_stream:
        results.append(item)

    # Should have partial response first, then final response
    assert len(results) >= 1
    # Final response should be present
    final_result = results[-1]
    assert final_result.output == "Final response after partial"


@pytest.mark.asyncio
async def test_recursion_invoke_with_function_calls_recursive_path(
    teal_agents_handler, mocker, agent_task
):
    """
    Test recursion_invoke with function calls that trigger recursive call.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request"

    # Mock state loading
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    # Mock agent building
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mock_agent.get_model_type.return_value = "test_model"

    # Create response with function calls
    response_with_function_call = ChatMessageContent(
        role=AuthorRole.ASSISTANT,
        items=[
            FunctionCallContent(
                name="test_function", plugin_name="test_plugin", arguments={"arg": "value"}
            )
        ],
    )

    call_count = 0

    # Create a custom mock for chat completion service that returns
    # function call first, then normal response
    class TestChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model"

        async def get_chat_message_contents(self, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call returns function call
                return [response_with_function_call]
            else:
                # Second call returns normal response
                return [ChatMessageContent(role=AuthorRole.ASSISTANT, content="Final response")]

    mock_chat_completion_service = TestChatCompletionService()
    mock_settings = {}
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    # Mock function invocation
    mock_function_result = MagicMock()
    mock_function_result.to_chat_message_content.return_value = ChatMessageContent(
        role=AuthorRole.ASSISTANT, content="Function executed successfully"
    )
    mocker.patch.object(
        TealAgentsV1Alpha1Handler, "_invoke_function", return_value=mock_function_result
    )

    # Mock hitl_manager.check_for_intervention to return False
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.hitl_manager.check_for_intervention",
        return_value=False,
    )

    # Call recursion_invoke
    result = await teal_agents_handler.recursion_invoke(
        inputs=chat_history, session_id=session_id, task_id=task_id, request_id=request_id
    )

    # Should return the final response after executing function calls
    assert result.output == "Final response"
    assert call_count == 2  # Should have made recursive call


@pytest.mark.asyncio
async def test_recursion_invoke_stream_with_extra_data_partial(
    teal_agents_handler, mocker, agent_task
):
    """
    Test recursion_invoke_stream with ExtraDataPartial parsing.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request"

    # Mock state loading
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    # Mock agent building
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mock_agent.get_model_type.return_value = "test_model"

    # Create streaming content with valid ExtraDataPartial JSON
    valid_extra_data_json = '{"extra_data": [{"key": "value"}]}'
    streaming_content = StreamingChatMessageContent(
        role=AuthorRole.ASSISTANT, content=valid_extra_data_json, choice_index=0
    )

    # Create a custom mock for chat completion service
    class TestChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model"

        async def get_chat_message_contents(self, **kwargs):
            return [streaming_content]

    mock_chat_completion_service = TestChatCompletionService()
    mock_settings = {}
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    # Mock prepare_agent_response
    mock_response = TealAgentsResponse(
        session_id=session_id,
        task_id=task_id,
        request_id=request_id,
        output="Final response with extra data",
        source="test",
        token_usage=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    mocker.patch.object(teal_agents_handler, "prepare_agent_response", return_value=mock_response)

    # Call the streaming method
    result_stream = teal_agents_handler.recursion_invoke_stream(
        chat_history, session_id, task_id, request_id
    )

    # Collect results
    results = []
    async for item in result_stream:
        results.append(item)

    # Should have final response
    assert len(results) >= 1
    final_result = results[-1]
    assert final_result.output == "Final response with extra data"


@pytest.mark.asyncio
async def test_recursion_invoke_stream_with_function_calls_and_recursion(
    teal_agents_handler, mocker, agent_task
):
    """
    Test recursion_invoke_stream with function calls triggering recursion.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request"

    # Mock state loading
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    # Mock agent building
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mock_agent.get_model_type.return_value = "test_model"

    # Create response with function calls
    response_with_function_call = StreamingChatMessageContent(
        role=AuthorRole.ASSISTANT,
        choice_index=0,
        items=[
            FunctionCallContent(
                name="test_function", plugin_name="test_plugin", arguments={"arg": "value"}
            )
        ],
    )

    call_count = 0

    # Create a custom mock for chat completion service
    class TestChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model"

        async def get_chat_message_contents(self, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call returns function call
                return [response_with_function_call]
            else:
                # Subsequent calls return normal response
                return [
                    StreamingChatMessageContent(
                        role=AuthorRole.ASSISTANT,
                        content="Recursive streaming response",
                        choice_index=0,
                    )
                ]

    mock_chat_completion_service = TestChatCompletionService()
    mock_settings = {}
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    # Mock function invocation
    mock_function_result = MagicMock()
    mock_function_result.to_chat_message_content.return_value = ChatMessageContent(
        role=AuthorRole.ASSISTANT, content="Function executed"
    )
    mocker.patch.object(
        TealAgentsV1Alpha1Handler, "_invoke_function", return_value=mock_function_result
    )

    # Mock hitl_manager.check_for_intervention to return False
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.hitl_manager.check_for_intervention",
        return_value=False,
    )

    # Mock prepare_agent_response for recursive calls
    mock_response = TealAgentsResponse(
        session_id=session_id,
        task_id=task_id,
        request_id=request_id,
        output="Final recursive response",
        source="test",
        token_usage=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    mocker.patch.object(teal_agents_handler, "prepare_agent_response", return_value=mock_response)

    # Call the streaming method
    result_stream = teal_agents_handler.recursion_invoke_stream(
        chat_history, session_id, task_id, request_id
    )

    # Collect results
    results = []
    async for item in result_stream:
        results.append(item)

    # Should have results from recursive call
    assert len(results) >= 1
    assert call_count >= 2  # Should have made recursive calls


@pytest.mark.asyncio
async def test_recursion_invoke_stream_hitl_exception(teal_agents_handler, mocker, agent_task):
    """
    Test recursion_invoke_stream with HITL intervention exception.
    """
    chat_history = ChatHistory()
    session_id = agent_task.session_id
    task_id = agent_task.task_id
    request_id = "test_request"

    # Mock state loading
    mocker.patch.object(teal_agents_handler.state, "load_by_request_id", return_value=agent_task)

    # Mock agent building
    mock_agent = MagicMock()
    mock_agent.agent.kernel = MagicMock()
    mock_agent.get_model_type.return_value = "test_model"

    # Create response with function calls
    response_with_function_call = StreamingChatMessageContent(
        role=AuthorRole.ASSISTANT,
        choice_index=0,
        items=[
            FunctionCallContent(
                name="intervention_function", plugin_name="test_plugin", arguments={"arg": "value"}
            )
        ],
    )

    # Create a custom mock for chat completion service
    class TestChatCompletionService(ChatCompletionClientBase):
        ai_model_id: str = "test_model"

        async def get_chat_message_contents(self, **kwargs):
            return [response_with_function_call]

    mock_chat_completion_service = TestChatCompletionService()
    mock_settings = {}
    mock_agent.agent.kernel.select_ai_service.return_value = (
        mock_chat_completion_service,
        mock_settings,
    )

    mocker.patch.object(teal_agents_handler.agent_builder, "build_agent", return_value=mock_agent)
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response",
        return_value=TokenUsage(completion_tokens=10, prompt_tokens=20, total_tokens=30),
    )

    # Mock hitl_manager.check_for_intervention to return True, triggering intervention
    mocker.patch(
        "sk_agents.tealagents.v1alpha1.agent.handler.hitl_manager.check_for_intervention",
        return_value=True,
    )

    # Mock the HITL exception management
    mock_hitl_response = HitlResponse(
        session_id=session_id,
        task_id=task_id,
        request_id=request_id,
        message="HITL intervention required",
        approval_url="http://example.com/approve",
        rejection_url="http://example.com/reject",
        tool_calls=[],
    )

    mocker.patch.object(
        teal_agents_handler, "_manage_hitl_exception", return_value=mock_hitl_response
    )

    # Call the streaming method
    result_stream = teal_agents_handler.recursion_invoke_stream(
        chat_history, session_id, task_id, request_id
    )

    # Collect results
    results = []
    async for item in result_stream:
        results.append(item)

    # Should have HITL response
    assert len(results) == 1
    assert isinstance(results[0], HitlResponse)
    assert results[0].message == "HITL intervention required"


@pytest.mark.asyncio
async def test_recursion_invoke_stream_extradata_success():
    """Test recursion_invoke_stream successful ExtraDataPartial parsing."""
    # Create a proper config using the same pattern as the fixture
    test_agent = AgentConfig(
        name="TestAgent",
        model="gpt-4o",
        system_prompt="test prompt",
        temperature=0.5,
        plugins=None,
    )
    config = BaseConfig(
        apiVersion="tealagents/v1alpha1",
        name="TestAgent",
        version=0.1,
        description="test agent",
        spec=Spec(agent=test_agent),
    )

    mock_app_config = MagicMock()
    mock_app_config.get.side_effect = lambda key: {
        TA_PERSISTENCE_MODULE.env_name: TA_PERSISTENCE_MODULE.default_value,
        TA_PERSISTENCE_CLASS.env_name: TA_PERSISTENCE_CLASS.default_value,
    }.get(key, MagicMock())

    mock_state_manager = MagicMock(spec=TaskPersistenceManager)
    mock_agent_builder = MagicMock(spec=AgentBuilder)

    handler = TealAgentsV1Alpha1Handler(
        config=config,
        app_config=mock_app_config,
        agent_builder=mock_agent_builder,
        state_manager=mock_state_manager,
    )

    # Create a mock agent task in state
    mock_agent_task = Mock()
    mock_agent_task.session_id = "test_session"
    mock_agent_task.task_id = "test_task"
    mock_agent_task.request_id = "test_request"
    mock_state_manager.load_by_request_id.return_value = mock_agent_task

    # Mock the agent builder and agent
    mock_agent = Mock()
    mock_kernel = Mock()
    mock_agent.agent.kernel = mock_kernel
    mock_agent.agent.arguments = {}
    mock_agent.get_model_type.return_value = "gpt-4o"
    mock_agent_builder.build_agent.return_value = mock_agent

    # Mock the chat completion client
    mock_chat_completion_client = AsyncMock(spec=ChatCompletionClientBase)

    # Create a mock response with content that will successfully parse as ExtraDataPartial
    response = ChatMessageContent(
        role=AuthorRole.ASSISTANT, content='{"extra_data": [{"key": "value"}]}'
    )

    # Mock get_chat_message_contents to return our response
    mock_chat_completion_client.get_chat_message_contents.return_value = [response]

    # Mock agent selection to return our mock client
    mock_kernel.select_ai_service.return_value = (mock_chat_completion_client, {})

    # Mock ExtraDataPartial.new_from_json to succeed and return data
    with patch("sk_agents.tealagents.v1alpha1.agent.handler.ExtraDataPartial") as mock_extra_data:
        mock_extra_data_partial = Mock()
        mock_extra_data_partial.extra_data = [{"key": "value"}]
        mock_extra_data.new_from_json.return_value = mock_extra_data_partial

        # Mock token usage calculation
        with patch(
            "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response"
        ) as mock_token_usage:
            mock_token_usage.return_value = TokenUsage(
                completion_tokens=10, prompt_tokens=20, total_tokens=30
            )

            chat_history = ChatHistory()
            chat_history.add_user_message("test message")
            session_id = "test_session"
            task_id = "test_task"
            request_id = "test_request"

            # Execute the recursion_invoke_stream
            result_gen = handler.recursion_invoke_stream(
                chat_history, session_id, task_id, request_id
            )
            results = []
            async for result in result_gen:
                results.append(result)

            # Should get a final response since ExtraDataPartial parsing succeeded
            assert len(results) >= 1
            # Verify that extra_data_collector.add_extra_data_items was called
            mock_extra_data.new_from_json.assert_called_once_with(
                '{"extra_data": [{"key": "value"}]}'
            )


@pytest.mark.asyncio
async def test_recursion_invoke_stream_extradata_exception_with_content():
    """Test recursion_invoke_stream ExtraDataPartial exception handling with content > 0."""
    # Create a proper config using the same pattern as the fixture
    test_agent = AgentConfig(
        name="TestAgent",
        model="gpt-4o",
        system_prompt="test prompt",
        temperature=0.5,
        plugins=None,
    )
    config = BaseConfig(
        apiVersion="tealagents/v1alpha1",
        name="TestAgent",
        version=0.1,
        description="test agent",
        spec=Spec(agent=test_agent),
    )

    mock_app_config = MagicMock()
    mock_app_config.get.side_effect = lambda key: {
        TA_PERSISTENCE_MODULE.env_name: TA_PERSISTENCE_MODULE.default_value,
        TA_PERSISTENCE_CLASS.env_name: TA_PERSISTENCE_CLASS.default_value,
    }.get(key, MagicMock())

    mock_state_manager = MagicMock(spec=TaskPersistenceManager)
    mock_agent_builder = MagicMock(spec=AgentBuilder)

    handler = TealAgentsV1Alpha1Handler(
        config=config,
        app_config=mock_app_config,
        agent_builder=mock_agent_builder,
        state_manager=mock_state_manager,
    )

    # Create a mock agent task in state
    mock_agent_task = Mock()
    mock_agent_task.session_id = "test_session"
    mock_agent_task.task_id = "test_task"
    mock_agent_task.request_id = "test_request"
    mock_state_manager.load_by_request_id.return_value = mock_agent_task

    # Mock the agent builder and agent
    mock_agent = Mock()
    mock_kernel = Mock()
    mock_agent.agent.kernel = mock_kernel
    mock_agent.agent.arguments = {}
    mock_agent.get_model_type.return_value = "gpt-4o"
    mock_agent_builder.build_agent.return_value = mock_agent

    # Mock the chat completion client
    mock_chat_completion_client = AsyncMock(spec=ChatCompletionClientBase)

    # Create a mock response with content that will trigger ExtraDataPartial parsing
    response = ChatMessageContent(role=AuthorRole.ASSISTANT, content="invalid json content")

    # Mock get_chat_message_contents to return our response
    mock_chat_completion_client.get_chat_message_contents.return_value = [response]

    # Mock agent selection to return our mock client
    mock_kernel.select_ai_service.return_value = (mock_chat_completion_client, {})

    # Mock ExtraDataPartial.new_from_json to raise exception
    with patch("sk_agents.tealagents.v1alpha1.agent.handler.ExtraDataPartial") as mock_extra_data:
        mock_extra_data.new_from_json.side_effect = Exception("JSON parse error")

        # Mock token usage calculation
        with patch(
            "sk_agents.tealagents.v1alpha1.agent.handler.get_token_usage_for_response"
        ) as mock_token_usage:
            mock_token_usage.return_value = TokenUsage(
                completion_tokens=10, prompt_tokens=20, total_tokens=30
            )

            chat_history = ChatHistory()
            chat_history.add_user_message("test message")
            session_id = "test_session"
            task_id = "test_task"
            request_id = "test_request"

            # Execute the recursion_invoke_stream
            result_gen = handler.recursion_invoke_stream(
                chat_history, session_id, task_id, request_id
            )
            results = []
            async for result in result_gen:
                results.append(result)

            # Should get a partial response with the content since len(response.content) > 0
            # followed by a final response
            assert len(results) >= 1
            assert isinstance(results[0], TealAgentsPartialResponse)
            assert results[0].output_partial == "invalid json content"


@pytest.mark.asyncio
async def test_recursion_invoke_stream_general_exception():
    """Test recursion_invoke_stream general exception handling."""
    # Create a proper config using the same pattern as the fixture
    test_agent = AgentConfig(
        name="TestAgent",
        model="gpt-4o",
        system_prompt="test prompt",
        temperature=0.5,
        plugins=None,
    )
    config = BaseConfig(
        apiVersion="tealagents/v1alpha1",
        name="TestAgent",
        version=0.1,
        description="test agent",
        spec=Spec(agent=test_agent),
    )

    mock_app_config = MagicMock()
    mock_app_config.get.side_effect = lambda key: {
        TA_PERSISTENCE_MODULE.env_name: TA_PERSISTENCE_MODULE.default_value,
        TA_PERSISTENCE_CLASS.env_name: TA_PERSISTENCE_CLASS.default_value,
    }.get(key, MagicMock())

    mock_state_manager = MagicMock(spec=TaskPersistenceManager)
    mock_agent_builder = MagicMock(spec=AgentBuilder)

    handler = TealAgentsV1Alpha1Handler(
        config=config,
        app_config=mock_app_config,
        agent_builder=mock_agent_builder,
        state_manager=mock_state_manager,
    )

    # Create a mock agent task in state
    mock_agent_task = Mock()
    mock_agent_task.session_id = "test_session"
    mock_agent_task.task_id = "test_task"
    mock_agent_task.request_id = "test_request"
    mock_state_manager.load_by_request_id.return_value = mock_agent_task

    # Mock the agent builder and agent - but make chat completion client fail
    mock_agent = Mock()
    mock_kernel = Mock()
    mock_agent.agent.kernel = mock_kernel
    mock_agent.agent.arguments = {}
    mock_agent.get_model_type.return_value = "gpt-4o"
    mock_agent_builder.build_agent.return_value = mock_agent

    # Mock the chat completion client to raise exception during streaming
    mock_chat_completion_client = AsyncMock(spec=ChatCompletionClientBase)
    mock_chat_completion_client.get_chat_message_contents.side_effect = Exception("Stream error")

    # Mock agent selection to return our mock client
    mock_kernel.select_ai_service.return_value = (mock_chat_completion_client, {})

    chat_history = ChatHistory()
    chat_history.add_user_message("test message")
    session_id = "test_session"
    task_id = "test_task"
    request_id = "test_request"

    # Execute and expect AgentInvokeException
    result_gen = handler.recursion_invoke_stream(chat_history, session_id, task_id, request_id)
    with pytest.raises(AgentInvokeException) as exc_info:
        # Force evaluation of the async generator to trigger the exception
        results = []
        async for result in result_gen:
            results.append(result)

    # Check that the exception message contains expected content
    assert "Error invoking stream for TestAgent:0.1" in str(exc_info.value)
    assert "test_session" in str(exc_info.value)
    assert "test_task" in str(exc_info.value)
