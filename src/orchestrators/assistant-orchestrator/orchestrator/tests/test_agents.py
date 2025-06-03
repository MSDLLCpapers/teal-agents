import pytest
import json
from agents import BaseAgent, AgentCatalog, FallbackAgent, AgentInput, ChatHistoryItem, FallbackInput
from pydantic import BaseModel
from ..model import Conversation



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
    return AgentCatalog(agents={
        "TestAgent": MockAgent(
            name='test agent',
            description='agent used for unit test',
            endpoint='ws://test_stream_endpoint',
            endpoint_api='http://test_api_endpoint',
            api_key='test_key'
        )
    })

@pytest.fixture
def multiple_agent_catalog():
    return AgentCatalog(agents={
        "TestMathAgent": MockAgent(
            name='Math Agent',
            description='Math Agent used for unit test',
            endpoint='ws://test_stream_endpoint',
            endpoint_api='http://test_api_endpoint',
            api_key='test_key'
        ),
        "TestWeatherAgent": MockAgent(
            name='Weather Agent',
            description='Weather Agent used for unit test',
            endpoint='ws://test_stream_endpoint',
            endpoint_api='http://test_api_endpoint',
            api_key='test_key'
        ),
        "TestNewsAgent": MockAgent(
            name='News Agent',
            description='News Agent used for unit test',
            endpoint='ws://test_stream_endpoint',
            endpoint_api='http://test_api_endpoint',
            api_key='test_key'
        )
    })

@pytest.fixture
def fallback_agent_base_params():
    return {
        "name": "Fallback",
        "description": "A fallback agent",
        "endpoint": "ws://fallback",
        "endpoint_api": "http://fallback_api",
        "api_key": "fallback_key"
    }

@pytest.fixture        
def agent_instance():
    agent = MockAgent(
        name='test agent',
        description='agent used for unit test',
        endpoint='ws://test_stream_endpoint',
        endpoint_api='http://test_api_endpoint',
        api_key='test_key'
    )
    return agent

@pytest.fixture        
def conversation_for_testing():
    return Conversation(
        conversation_id= 'test-id',
        user_id= 'test-iser',
        history= [],
        user_context= {}
    )

def test_agent_get_invoke_input(agent_instance):
    agent_input = _AgentInput(data="Test Hello World")
    response = agent_instance.get_invoke_input(agent_input)

    assert response == "Processed input: Test Hello World"

def test_invoke_api_success(mocker, agent_instance, conversation_for_testing):
    _conversation_to_agent_input = mocker.patch("agents._conversation_to_agent_input", return_value=_AgentInput(data="mocked input"))

    # Mock requests.post
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success", "data": "response_from_api"}
    post_request = mocker.patch('requests.post', return_value=mock_response)

    response = agent_instance.invoke_api(conversation_for_testing, authorization="xyz")
    
    _conversation_to_agent_input.assert_called_once_with(conversation_for_testing)

    expected_headers = {
        "taAgwKey": agent_instance.api_key,
        "Authorization": "xyz",
        "Content-Type": "application/json"
    }

    post_request.assert_called_once_with(
            agent_instance.endpoint_api,
            data="Processed input: mocked input",
            headers=expected_headers
        )
    
    assert response == {"status": "success", "data": "response_from_api"}


def test_invoke_api_non_200_status(mocker, agent_instance, conversation_for_testing):
    _conversation_to_agent_input = mocker.patch("agents._conversation_to_agent_input", return_value=_AgentInput(data="mocked input"))
    
    mock_response = mocker.Mock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    post_request = mocker.patch('requests.post', return_value=mock_response)

    with pytest.raises(Exception) as excinfo:
        agent_instance.invoke_api(conversation_for_testing)
    
    
def test_multiple_agents_catalog(fallback_agent_base_params, multiple_agent_catalog):
    agent_input = AgentInput(
        chat_history=[
            ChatHistoryItem(
                role="user",
                content="hi this is a test"
            )
        ],
        user_context={}
    )

    fallback_agent = FallbackAgent(
        agent_catalog = multiple_agent_catalog,
        **fallback_agent_base_params
    )

    response = fallback_agent.get_invoke_input(agent_input)
    
    result_data = json.loads(response)
    
    expected_result = FallbackInput(
        chat_history=agent_input.chat_history,
        user_context=agent_input.user_context,
        agents=multiple_agent_catalog.agents
    )
    expected_result = expected_result.model_dump(mode='json')
    print('***Expected result: ',expected_result)
    assert result_data == expected_result
