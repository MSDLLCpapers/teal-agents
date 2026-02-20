import pytest

from agents import AgentCatalog, RecipientChooserAgent
from model.conversation import Conversation
from recipient_chooser import RecipientChooser, SelectedAgent


@pytest.fixture
def recipient_chooser_agent_fixture():
    agent_catalog = AgentCatalog(agents={})
    rec_chooser_agent = RecipientChooserAgent(
        name="TestChooserAgent",
        description="TestChooserAgent description",
        endpoint="http://TestChooserAgent/0.1",
        endpoint_api="http://TestChooserAgent/0.1",
        api_key="some-key",
        agent_catalog=agent_catalog,
    )
    return rec_chooser_agent


@pytest.fixture
def choose_recipient_fixture():
    message = "Test message"
    conversation = Conversation(
        conversation_id="test_conversation_id", user_id="testuser", history=[], user_context={}
    )
    return message, conversation


@pytest.fixture
def mocker_response_fixture(mocker):
    mock_response = mocker.Mock()
    mocker.patch("requests.post", return_value=mock_response)
    yield mock_response


async def test_choose_recipient(
    recipient_chooser_agent_fixture, choose_recipient_fixture, mocker_response_fixture
):
    selected_agent = SelectedAgent(agent_name="TestAgent:0.1", confidence="High", is_followup=True)
    mock_post_response = {
        "token_usage": {"completion_tokens": 35, "prompt_tokens": 782, "total_tokens": 817},
        "extra_data": None,
        "output_raw": '```json\n{\n  "agent_name": "TestAgent:0.1",\n  "confidence": "High",\n \
            "is_followup": true\n}\n```',
        "output_pydantic": None,
    }
    message, conversation = choose_recipient_fixture
    mocker_response_fixture.json.return_value = mock_post_response
    rec_chooser = RecipientChooser(recipient_chooser_agent_fixture)
    sel_agent = await rec_chooser.choose_recipient(message=message, conv=conversation)
    assert sel_agent == selected_agent


async def test_choose_recipient_with_auth(
    recipient_chooser_agent_fixture, choose_recipient_fixture, mocker_response_fixture
):
    # Expected selected agent
    expected = SelectedAgent(agent_name="TestAgent:0.1", confidence="High", is_followup=True)

    # Mocked backend response
    mock_post_response = {
        "token_usage": {"completion_tokens": 35, "prompt_tokens": 782, "total_tokens": 817},
        "extra_data": None,
        "output_raw": '```json\n{\n  "agent_name": "TestAgent:0.1",\n  "confidence": "High",\n '
        '            "is_followup": true\n}\n```',
        "output_pydantic": None,
    }
    message, conversation = choose_recipient_fixture
    mocker_response_fixture.json.return_value = mock_post_response
    rec_chooser = RecipientChooser(recipient_chooser_agent_fixture)
    # Provide authorization string (e.g., bearer token)
    authorization = "Bearer test-token-123"
    sel_agent = await rec_chooser.choose_recipient(
        message=message, conv=conversation, authorization=authorization
    )
    assert sel_agent == expected


async def test_choose_recipient_error(
    recipient_chooser_agent_fixture, choose_recipient_fixture, mocker_response_fixture
):
    message, conversation = choose_recipient_fixture
    mocker_response_fixture.json.return_value = None
    rec_chooser = RecipientChooser(recipient_chooser_agent_fixture)
    with pytest.raises(Exception) as excinfo:
        await rec_chooser.choose_recipient(message=message, conv=conversation)
    assert str(excinfo.value) == "Unable to determine recipient"


def test_clean_output_errors():
    with pytest.raises(Exception) as excinfo:
        RecipientChooser._clean_output("{")
    assert str(excinfo.value) == "Invalid response"
    with pytest.raises(Exception) as excinfo:
        RecipientChooser._clean_output("}")
    assert str(excinfo.value) == "Invalid response"
