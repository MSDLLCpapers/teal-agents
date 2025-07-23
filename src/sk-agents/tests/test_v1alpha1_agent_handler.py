from datetime import datetime
from unittest.mock import MagicMock

import pytest
from semantic_kernel.contents import ChatMessageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.utils.author_role import AuthorRole

from sk_agents.exceptions import AgentInvokeException, AuthenticationException
from sk_agents.ska_types import BaseConfig, ContentType, MultiModalItem, TokenUsage
from sk_agents.tealagents.models import (
    AgentTask,
    AgentTaskItem,
    TealAgentsResponse,
    UserMessage,
)
from sk_agents.tealagents.v1alpha1.agent.config import Spec
from sk_agents.tealagents.v1alpha1.agent.handler import TealAgentsV1Alpha1Handler
from sk_agents.tealagents.v1alpha1.agent_builder import AgentBuilder
from sk_agents.tealagents.v1alpha1.config import AgentConfig


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
def teal_agents_handler(mock_config, mock_agent_builder):
    """Provides an initialized TealAgentsV1Alpha1Handler instance."""
    return TealAgentsV1Alpha1Handler(config=mock_config, agent_builder=mock_agent_builder)


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
def agent_response(agent_task):
    return TealAgentsResponse(
        session_id=agent_task.session_id,
        task_id=agent_task.task_id,
        request_id="test_request_id",
        output="This is the agent's response.",
        token_usage=TokenUsage(completion_tokens=100, prompt_tokens=200, total_tokens=300),
    )


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


def test_authenticate_user_success(teal_agents_handler, mocker):
    """
    Test that authenticate_user successfully returns a user ID
    when authorization is successful.
    """
    test_token = "valid_auth_token_123"
    expected_user_id = "authenticated_user_id"
    mocker.patch.object(
        teal_agents_handler.authorizer, "authorize_request", return_value=expected_user_id
    )

    user_id = teal_agents_handler.authenticate_user(token=test_token)

    assert user_id == expected_user_id
    teal_agents_handler.authorizer.authorize_request.assert_called_once_with(auth_header=test_token)


def test_authenticate_user_failure(teal_agents_handler, mocker):
    """
    Test that authenticate_user raises an AuthenticationException
    when authorization fails.
    """

    test_token = "invalid_auth_token_xyz"
    mock_exception_message = "Token is expired"
    mock_original_exception = ValueError(mock_exception_message)

    mocker.patch.object(
        teal_agents_handler.authorizer, "authorize_request", side_effect=mock_original_exception
    )

    with pytest.raises(AuthenticationException):
        teal_agents_handler.authenticate_user(token=test_token)


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
async def test_manage_incoming_task_load_success(teal_agents_handler, mocker, user_message):
    """
    Test _manage_incoming_task when the task is successfully loaded from state.
    """
    task_id = user_message.task_id
    session_id = user_message.session_id
    user_id = "test_user"
    request_id = "test_request_id"

    mock_loaded_task = mocker.MagicMock(spec=AgentTask, task_id=task_id, status="Running")
    mocker.patch.object(teal_agents_handler.state, "load", return_value=mock_loaded_task)
    mocker.patch.object(teal_agents_handler.state, "create")

    result_task = await teal_agents_handler._manage_incoming_task(
        task_id=task_id,
        session_id=session_id,
        user_id=user_id,
        request_id=request_id,
        inputs=user_message,
    )
    assert isinstance(result_task, AgentTask)

    assert result_task == mock_loaded_task
    teal_agents_handler.state.load.assert_called_once_with(task_id)
    teal_agents_handler.state.create.assert_not_called()


def test_validate_user_id_success(user_message):
    """
    Test that _validate_user_id does not raise an exception when user_id matches.
    """
    user_id = "test_user"
    task_id = user_message.task_id
    agent_task = AgentTask(
        task_id=task_id,
        session_id="test_session",
        user_id=user_id,
        items=[],
        created_at=datetime.now(),
        last_updated=datetime.now(),
        status="Running",
    )

    try:
        TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)
    except AgentInvokeException:
        pytest.fail("AgentInvokeException was raised unexpectedly.")


def test_validate_user_id_failure(user_message):
    """
    Test that _validate_user_id does not raise an exception when user_id matches.
    """

    user_id = "test_user"
    task_id = user_message.task_id
    agent_task = AgentTask(
        task_id=task_id,
        session_id="test_session",
        user_id="mismatch_user_id",
        items=[],
        created_at=datetime.now(),
        last_updated=datetime.now(),
        status="Running",
    )
    with pytest.raises(AgentInvokeException):
        TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)


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
    teal_agents_handler, mocker, mock_config, user_message, agent_task, agent_response
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
    mocker.patch.object(teal_agents_handler, "_manage_incoming_task", return_value=agent_task)
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
        mock_user_id, mock_task_id, agent_task
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
