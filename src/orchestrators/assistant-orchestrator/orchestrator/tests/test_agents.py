import json

import pytest
from pydantic import BaseModel

from agents import (
    Agent,
    AgentBuilder,
    AgentCatalog,
    AgentInput,
    BaseAgent,
    ChatHistoryItem,
    FallbackAgent,
    FallbackInput,
    PromptAgent,
    RecipientChooserAgent,
)
from model import Conversation


class _AgentInput(BaseModel):
    data: str = "test_input_data"


class MockAgent(BaseAgent):
    def get_invoke_input(self, agent_input: _AgentInput) -> str:
        return f"Processed input: {agent_input.data}"


@pytest.fixture
def empty_agent_catalog():
    return AgentCatalog(agents={})


@pytest.fixture
def single_agent_catalog():
    return AgentCatalog(
        agents={
            "TestAgent": MockAgent(
                name="test agent",
                description="agent used for unit test",
                endpoint="ws://test_stream_endpoint",
                endpoint_api="http://test_api_endpoint",
                api_key="test_key",
            )
        }
    )


@pytest.fixture
def multiple_agent_catalog():
    return AgentCatalog(
        agents={
            "TestMathAgent": MockAgent(
                name="Math Agent",
                description="Math Agent used for unit test",
                endpoint="ws://test_stream_endpoint",
                endpoint_api="http://test_api_endpoint",
                api_key="test_key",
            ),
            "TestWeatherAgent": MockAgent(
                name="Weather Agent",
                description="Weather Agent used for unit test",
                endpoint="ws://test_stream_endpoint",
                endpoint_api="http://test_api_endpoint",
                api_key="test_key",
            ),
            "TestNewsAgent": MockAgent(
                name="News Agent",
                description="News Agent used for unit test",
                endpoint="ws://test_stream_endpoint",
                endpoint_api="http://test_api_endpoint",
                api_key="test_key",
            ),
        }
    )


@pytest.fixture
def fallback_agent_base_params():
    return {
        "name": "Fallback",
        "description": "A fallback agent",
        "endpoint": "ws://fallback",
        "endpoint_api": "http://fallback_api",
        "api_key": "fallback_key",
    }


@pytest.fixture
def agent_instance():
    agent = MockAgent(
        name="test agent",
        description="agent used for unit test",
        endpoint="ws://test_stream_endpoint",
        endpoint_api="http://test_api_endpoint",
        api_key="test_key",
    )
    return agent


@pytest.fixture
def conversation_for_testing():
    return Conversation(conversation_id="test-id", user_id="test-user", history=[], user_context={})


@pytest.fixture
def secure_builder(mocker):
    mocker.patch("ska_utils.strtobool", return_value=True)
    return AgentBuilder(agpt_gw_host="test.secure.host", agpt_gw_secure="true")


@pytest.fixture
def insecure_builder(mocker):
    mocker.patch("ska_utils.strtobool", return_value=False)
    return AgentBuilder(agpt_gw_host="test.insecure.host", agpt_gw_secure="false")


@pytest.fixture
def mock_successful_openapi_response_get(mocker):
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "openapi": "3.1.0",
        "info": {"title": "FastAPI", "version": "0.1.0"},
        "paths": {
            "/TestAgent/0.1": {
                "post": {"summary": "Invoke", "description": "Test agent description"}
            }
        },
    }
    mock_request_get = mocker.patch("requests.get", return_value=mock_response)
    return mock_request_get


@pytest.fixture
def mock_failed_openapi_request_get(mocker):
    mock_request = mocker.patch("requests.get", return_value=None)
    return mock_request


def test_agent_get_invoke_input(agent_instance):
    agent_input = _AgentInput(data="Test Hello World")
    response = agent_instance.get_invoke_input(agent_input)

    assert response == "Processed input: Test Hello World"


def test_invoke_api_success(mocker, agent_instance, conversation_for_testing):
    _conversation_to_agent_input = mocker.patch(
        "agents._conversation_to_agent_input", return_value=_AgentInput(data="mocked input")
    )

    # Mock requests.post
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success", "data": "response_from_api"}
    post_request = mocker.patch("requests.post", return_value=mock_response)

    response = agent_instance.invoke_api(conversation_for_testing, authorization="xyz")

    _conversation_to_agent_input.assert_called_once_with(conversation_for_testing, None)

    expected_headers = {
        "taAgwKey": agent_instance.api_key,
        "Authorization": "xyz",
        "Content-Type": "application/json",
    }

    post_request.assert_called_once_with(
        agent_instance.endpoint_api, data="Processed input: mocked input", headers=expected_headers
    )

    assert response == {"status": "success", "data": "response_from_api"}


def test_invoke_api_non_200_status(mocker, agent_instance, conversation_for_testing):
    mocker.patch(
        "agents._conversation_to_agent_input", return_value=_AgentInput(data="mocked input")
    )

    mock_response = mocker.Mock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    mocker.patch("requests.post", return_value=mock_response)

    with pytest.raises(
        Exception,
        match=f"Failed to invoke agent API: {mock_response.status_code} - {mock_response.text}",
    ):
        agent_instance.invoke_api(conversation_for_testing)


def test_multiple_agents_catalog(fallback_agent_base_params, multiple_agent_catalog):
    agent_input = AgentInput(
        chat_history=[ChatHistoryItem(role="user", content="hi this is a test")], user_context={}
    )

    fallback_agent = FallbackAgent(
        agent_catalog=multiple_agent_catalog, **fallback_agent_base_params
    )

    response = fallback_agent.get_invoke_input(agent_input)

    result_data = json.loads(response)

    expected_result = FallbackInput(
        chat_history=agent_input.chat_history,
        user_context=agent_input.user_context,
        agents=[
            PromptAgent(name=value.name, description=value.description)
            for value in multiple_agent_catalog.agents.values()
        ],
    )
    expected_result = expected_result.model_dump(mode="json")

    assert result_data == expected_result


def test_agent_builder_init_secure(mocker):
    mocker.patch("ska_utils.strtobool", return_value=True)
    builder = AgentBuilder(agpt_gw_host="host.com", agpt_gw_secure="true")

    assert builder.agpt_gw_host == "host.com"
    assert builder.agpt_gw_secure is True


def test_agent_builder_init_insecure(mocker):
    mocker.patch("ska_utils.strtobool", return_value=False)
    builder = AgentBuilder(agpt_gw_host="host.com", agpt_gw_secure="false")

    assert builder.agpt_gw_host == "host.com"
    assert builder.agpt_gw_secure is False


def test_http_or_https_secure(secure_builder):
    assert secure_builder._http_or_https() == "https"


def test_http_or_https_insecure(insecure_builder):
    assert insecure_builder._http_or_https() == "http"


def test_ws_or_wss_secure(secure_builder):
    assert secure_builder._ws_or_wss() == "wss"


def test_ws_or_wss_insecure(insecure_builder):
    assert insecure_builder._ws_or_wss() == "ws"


@pytest.mark.parametrize(
    "agent_name, expected_path",
    [
        ("group:name", "group/name"),
        ("my_group:my_agent", "my_group/my_agent"),
    ],
)
def test_agent_to_path(agent_name, expected_path):
    assert AgentBuilder._agent_to_path(agent_name) == expected_path


def test_agent_to_path_no_version():
    agent_name = "AgentNoVersion"
    with pytest.raises(
        Exception, match=f"Expected 'AgentName':version. Ex: ExampleAgent:0.1. Got {agent_name}"
    ):
        AgentBuilder._agent_to_path(agent_name)


def test_get_agent_description_success(secure_builder, mock_successful_openapi_response_get):
    description = secure_builder._get_agent_description("test:agent")
    assert description == "Test agent description"

    mock_successful_openapi_response_get.assert_called_once_with(
        "https://test.secure.host/test/agent/openapi.json"
    )


def test_get_agent_description_failure(insecure_builder, mock_failed_openapi_request_get):
    agent_name = "testagent:0.1"
    with pytest.raises(Exception, match=f"Failed to get agent description for {agent_name}"):
        insecure_builder._get_agent_description(agent_name)

    mock_failed_openapi_request_get.assert_called_once_with(
        "http://test.insecure.host/testagent/0.1/openapi.json"
    )


def test_build_agent(mocker, secure_builder):
    mock_get_description = mocker.patch.object(
        secure_builder, "_get_agent_description", return_value="Built agent description"
    )

    agent_name = "test_group:0.1"
    api_key = "test_api_key"

    agent = secure_builder.build_agent(agent_name, api_key)

    assert isinstance(agent, Agent)
    assert agent.name == agent_name
    assert agent.description == "Built agent description"
    assert agent.endpoint == "wss://test.secure.host/test_group/0.1/stream"
    assert agent.endpoint_api == "https://test.secure.host/test_group/0.1"
    assert agent.api_key == api_key
    mock_get_description.assert_called_once_with(agent_name)


def test_build_agent_description_failure(secure_builder, mocker):
    mocker.patch.object(
        secure_builder, "_get_agent_description", side_effect=Exception("Description failed")
    )

    with pytest.raises(Exception, match="Description failed"):
        secure_builder.build_agent("fail:agent", "key")


def test_build_fallback_agent_success(secure_builder, mocker, single_agent_catalog):
    mocker.patch.object(
        secure_builder, "_get_agent_description", return_value="Fallback description"
    )

    agent_name = "fallbackagent:0.1"
    api_key = "test_api_key"
    mock_agent_catalog = single_agent_catalog

    fallback_agent = secure_builder.build_fallback_agent(agent_name, api_key, mock_agent_catalog)

    assert isinstance(fallback_agent, FallbackAgent)
    assert fallback_agent.name == agent_name
    assert fallback_agent.description == "Fallback description"
    assert fallback_agent.endpoint == "wss://test.secure.host/fallbackagent/0.1/stream"
    assert fallback_agent.endpoint_api == "https://test.secure.host/fallbackagent/0.1"
    assert fallback_agent.api_key == api_key
    assert fallback_agent.agent_catalog is mock_agent_catalog
    secure_builder._get_agent_description.assert_called_once_with(agent_name)


def test_build_recipient_chooser_agent_success(secure_builder, mocker, single_agent_catalog):
    mocker.patch.object(
        secure_builder, "_get_agent_description", return_value="Recipient description"
    )

    agent_name = "recipientagent:0.1"
    api_key = "test_api_key"
    mock_agent_catalog = single_agent_catalog

    recipeint_agent = secure_builder.build_recipient_chooser_agent(
        agent_name, api_key, mock_agent_catalog
    )

    assert isinstance(recipeint_agent, RecipientChooserAgent)
    assert recipeint_agent.name == agent_name
    assert recipeint_agent.description == "Recipient description"
    assert recipeint_agent.endpoint == "https://test.secure.host/recipientagent/0.1"
    assert recipeint_agent.endpoint_api == "https://test.secure.host/recipientagent/0.1"
    assert recipeint_agent.api_key == api_key
    assert recipeint_agent.agent_catalog is mock_agent_catalog
    secure_builder._get_agent_description.assert_called_once_with(agent_name)
