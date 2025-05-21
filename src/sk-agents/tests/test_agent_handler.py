import pytest
from ska_utils import AppConfig

from sk_agents.ska_types import BaseConfig, BaseHandler
from sk_agents.skagents import handle
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
def mock_skagents_v1_handle(mocker):
    mock_response = V1_Handle_Response()
    mock_skagents_v1_handle = mocker.patch(
        "sk_agents.skagents.skagents_v1_handle", return_value=mock_response
    )
    return mock_skagents_v1_handle


def test_handler_valid_api(mock_skagents_v1_handle, config):
    app_config = AppConfig()
    authorization = "Bearer token"

    result = handle(config, app_config, authorization)

    mock_skagents_v1_handle.assert_called()
    assert isinstance(result, V1_Handle_Response)


def test_handler_no_authorization(mock_skagents_v1_handle, config):
    app_config = AppConfig()
    authorization = None

    result = handle(config, app_config, authorization)

    mock_skagents_v1_handle.assert_called()
    assert isinstance(result, V1_Handle_Response)


def test_handler_empty_api_version(mock_skagents_v1_handle, config):
    config.apiVersion = ""
    app_config = AppConfig()
    authorization = "Bearer token"

    with pytest.raises(ValueError):
        handle(config, app_config, authorization)
    mock_skagents_v1_handle.assert_not_called()


def test_handler_invalid_api(config, mock_skagents_v1_handle):
    app_config = AppConfig()
    authorization = "Bearer token"
    config.apiVersion = "invalid/invalid"

    with pytest.raises(ValueError):
        handle(config, app_config, authorization)
    mock_skagents_v1_handle.assert_not_called()


def test_handler_unknown_version(config, mock_skagents_v1_handle):
    app_config = AppConfig()
    authorization = "Bearer token"
    config.apiVersion = "skagents/unknown-version"

    with pytest.raises(ValueError):
        handle(config, app_config, authorization)
    mock_skagents_v1_handle.assert_not_called()
