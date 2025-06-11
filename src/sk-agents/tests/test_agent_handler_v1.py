import pytest
from ska_utils import AppConfig

from sk_agents.ska_types import BaseConfig, BaseHandler
from sk_agents.skagents.v1 import handle
from sk_agents.skagents.v1.config import AgentConfig
from sk_agents.skagents.v1.sequential.config import Spec, TaskConfig


@pytest.fixture
def config():
    test_agent = AgentConfig(
        name="test agent",
        model="test model",
        system_prompt="test prompt",
        plugins=None,
        remote_plugins=None,
    )

    task = TaskConfig(
        name="test name task",
        task_no=1,
        description="test task description",
        instructions="test task instruction",
        agent="test agent",
    )
    config = BaseConfig(
        apiVersion="skagents/v1",
        description="test-agent",
        service_name="TestAgent",
        version=0.1,
        input_type="BaseInput",
        output_type=None,
        spec=Spec(agents=[test_agent], tasks=[task]),
    )
    return config


class V1_Handle_Response(BaseHandler):
    async def invoke(self, inputs=None):
        pass

    async def invoke_stream(self, inputs=None):
        pass


@pytest.fixture
def mock_handle_chat(mocker):
    mock_response = V1_Handle_Response()
    mock_skagents_v1_handle = mocker.patch(
        "sk_agents.skagents.v1._handle_chat", return_value=mock_response
    )
    return mock_skagents_v1_handle


@pytest.fixture
def mock_handle_sequential(mocker):
    mock_response = V1_Handle_Response()
    mock_skagents_v1_handle = mocker.patch(
        "sk_agents.skagents.v1._handle_sequential", return_value=mock_response
    )
    return mock_skagents_v1_handle


def test_handle_valid_sequential(config, mock_handle_sequential):
    config.kind = "Sequential"
    app_config = AppConfig()
    authorization = "Bearer token"

    result = handle(config, app_config, authorization)

    mock_handle_sequential.assert_called_once()
    assert isinstance(result, V1_Handle_Response)


def test_handle_valid_chat(config, mock_handle_chat):
    config.kind = "Chat"
    app_config = AppConfig()
    authorization = "Bearer token"

    result = handle(config, app_config, authorization)

    mock_handle_chat.assert_called_once()
    assert isinstance(result, V1_Handle_Response)


def test_handle_valid_agent(config, mock_handle_chat):
    config.kind = "Agent"
    app_config = AppConfig()
    authorization = "Bearer token"

    result = handle(config, app_config, authorization)

    mock_handle_chat.assert_called_once()
    assert isinstance(result, V1_Handle_Response)


def test_handle_invalid_api_version(config, mock_handle_chat, mock_handle_sequential):
    config.apiVersion = "Invalid"
    app_config = AppConfig()
    authorization = "Bearer token"

    with pytest.raises(ValueError):
        handle(config, app_config, authorization)
    mock_handle_chat.assert_not_called()
    mock_handle_sequential.assert_not_called()


def test_handle_invalid_api_kind(config, mock_handle_chat, mock_handle_sequential):
    config.kind = "Invalid"
    app_config = AppConfig()
    authorization = "Bearer token"

    with pytest.raises(ValueError):
        handle(config, app_config, authorization)
    mock_handle_chat.assert_not_called()
    mock_handle_sequential.assert_not_called()


def test_handle_none_kind(config, mock_handle_chat, mock_handle_sequential):
    config.kind = "Bearer token"
    app_config = AppConfig()
    authorization = "Bearer token"

    with pytest.raises(ValueError):
        handle(config, app_config, authorization)
    mock_handle_chat.assert_not_called()
    mock_handle_sequential.assert_not_called()


def test_handle_missing_kind(config, mock_handle_chat, mock_handle_sequential):
    config.kind = ""
    app_config = AppConfig()
    authorization = "Bearer token"

    with pytest.raises(ValueError):
        handle(config, app_config, authorization)
    mock_handle_chat.assert_not_called()
    mock_handle_sequential.assert_not_called()
