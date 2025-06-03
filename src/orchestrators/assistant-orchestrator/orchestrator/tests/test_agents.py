import pytest
from agents import BaseAgent
from pydantic import BaseModel
from ..model import Conversation



class AgentInput(BaseModel):
    data: str = "test_input_data"


class MockAgent(BaseAgent):
    def get_invoke_input(self, agent_input: AgentInput) -> str:
        return f"Processed input: {agent_input.data}"

    

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
    agent_input = AgentInput(data="Test Hello World")
    response = agent_instance.get_invoke_input(agent_input)

    assert response == "Processed input: Test Hello World"

def test_invoke_api_success(mocker, agent_instance, conversation_for_testing):
    _conversation_to_agent_input = mocker.patch("agents._conversation_to_agent_input", return_value=AgentInput(data="mocked input"))

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
    _conversation_to_agent_input = mocker.patch("agents._conversation_to_agent_input", return_value=AgentInput(data="mocked input"))
    
    mock_response = mocker.Mock()
    mock_response.status_code = 404
    mock_response.text = "Not Found"
    post_request = mocker.patch('requests.post', return_value=mock_response)

    with pytest.raises(Exception) as excinfo:
        agent_instance.invoke_api(conversation_for_testing)
    
    
