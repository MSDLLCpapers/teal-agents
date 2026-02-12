import sys
from contextlib import nullcontext
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Mock configs and dependencies
mock_config_instance = MagicMock()
mock_config_instance.service_name = "assistant-orchestrator"
mock_config_instance.version = "v1"
mock_deps_module = MagicMock()
mock_deps_module.get_config.return_value = mock_config_instance
mock_deps_module.initialize = MagicMock()

# Setup sys for mock dependencies
sys.modules["routes.deps"] = mock_deps_module
sys.modules["deps"] = mock_deps_module

# Import app and routes: needs to be imported after mock dependencies
# ruff: noqa: E402
from jose import app as fastapi_app

# ruff: noqa: E402
from routes import apis

# Mocks for new_conversation endpoint dependencies and telemetry
# Disable telemetry for testing
mock_telemetry_instance = MagicMock()
mock_telemetry_instance.telemetry_enabled.return_value = False
# Mock the tracer and its start_as_current_span to return nullcontext
mock_telemetry_instance.tracer = MagicMock()
mock_telemetry_instance.tracer.start_as_current_span.return_value = nullcontext()

# Setup mock_conversation_object as a MagicMock to represent the conversation object and state
mock_conversation_object = MagicMock()
mock_conversation_object.conversation_id = "test_conv_id_123"
mock_conversation_object.user_id = "test_user_id_456"
mock_conversation_object.history = []  # This list will be mutated
mock_conversation_object.user_context = {}
mock_conv_manager_instance = MagicMock()


# Define side effects for conv_manager methods
def conv_manager_add_user_message_side_effect(conv_obj, message, agent_name):
    conv_obj.history.append({"content": message, "recipient": agent_name})


def conv_manager_add_agent_message_side_effect(conv_obj, message, agent_name):
    conv_obj.history.append({"content": message, "sender": agent_name})


def conv_manager_get_last_response_side_effect(conv_obj):
    return conv_obj.history


# Configure mocks to return mock_conversation_object instance
mock_conv_manager_instance.new_conversation = AsyncMock(return_value=mock_conversation_object)
# Set get_conversation to mock_conversation_object
mock_conv_manager_instance.get_conversation = AsyncMock(return_value=mock_conversation_object)
mock_conv_manager_instance.add_user_message = AsyncMock(
    side_effect=conv_manager_add_user_message_side_effect
)
mock_conv_manager_instance.add_agent_message = AsyncMock(
    side_effect=conv_manager_add_agent_message_side_effect
)
mock_conv_manager_instance.get_last_response = AsyncMock(
    side_effect=conv_manager_get_last_response_side_effect
)
mock_conv_manager_instance.add_transient_context = AsyncMock()

# --- Mocks for all dependencies ---
# Mock header_scheme for authorization
mock_header_scheme = MagicMock(return_value="Bearer dummy_token")
# Mock cache_user_context
mock_cache_user_context = MagicMock()
mock_user_context_cache_entry = MagicMock()
mock_user_context_cache_entry.model_dump.return_value = {"user_context": {"some_key": "some_value"}}
mock_cache_user_context.get_user_context_from_cache.return_value = mock_user_context_cache_entry
# Mock rec_chooser
mock_rec_chooser = MagicMock()
mock_selected_agent = MagicMock(agent_name="test_agent")  # Agent name that will be selected
mock_rec_chooser.choose_recipient = AsyncMock(return_value=mock_selected_agent)
# Mock agent_catalog
mock_agent_catalog = MagicMock()
mock_agent_instance = MagicMock()
mock_agent_instance.name = "test_agent"
# Simulate agent.invoke_api response
mock_agent_instance.invoke_api.return_value = {
    "output_raw": "Mocked agent response.",
    "extra_data": None,
}
mock_agent_catalog.agents = {"test_agent": mock_agent_instance}
# Mock fallback_agent
mock_fallback_agent = MagicMock()
mock_fallback_agent.name = "fallback_agent"


@pytest.fixture(scope="module")
def client():
    """
    Fixture that provides a synchronous test client for the FastAPI application.
    Patches module-level dependencies for the duration of the tests.
    """
    with (
        patch.object(apis, "get_telemetry", return_value=mock_telemetry_instance),
        patch.object(apis, "conv_manager", new=mock_conv_manager_instance),
        patch.object(apis, "header_scheme", new=mock_header_scheme),
        patch.object(apis, "cache_user_context", new=mock_cache_user_context),
        patch.object(apis, "rec_chooser", new=mock_rec_chooser),
        patch.object(apis, "agent_catalog", new=mock_agent_catalog),
        patch.object(apis, "fallback_agent", new=mock_fallback_agent),
    ):
        with TestClient(fastapi_app) as test_client:
            yield test_client


def test_healthcheck_endpoint(client: TestClient):
    """
    Test the /healthcheck endpoint to ensure it returns a healthy status.

    Args:
        client (TestClient): The synchronous test client.
    """
    expected_path = (
        f"/{mock_config_instance.service_name}/{mock_config_instance.version}/healthcheck"
    )

    # Make a synchronous GET request to the healthcheck endpoint
    response = client.get(expected_path)
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
    expected_response_data = {"status": "healthy"}
    assert response.json() == expected_response_data, (
        f"Expected response {expected_response_data}, got {response.json()}"
    )


def test_new_conversation_endpoint(client: TestClient):
    """
    Test the /conversations endpoint to start a new conversation.

    Args:
        client (TestClient): The synchronous test client.
    """
    # Reset history / user context at the start of the first test
    mock_conversation_object.history = []
    mock_conversation_object.user_context = {}
    mock_conv_manager_instance.new_conversation.reset_mock()
    mock_conv_manager_instance.get_conversation.reset_mock()
    mock_conv_manager_instance.add_user_message.reset_mock()
    mock_conv_manager_instance.add_agent_message.reset_mock()
    mock_conv_manager_instance.get_last_response.reset_mock()
    mock_conv_manager_instance.add_transient_context.reset_mock()
    mock_rec_chooser.choose_recipient.reset_mock()
    mock_agent_instance.invoke_api.reset_mock()

    user_id = "test_user_123"
    expected_conversation_id = mock_conversation_object.conversation_id
    expected_user_id = mock_conversation_object.user_id

    expected_path = (
        f"/{mock_config_instance.service_name}/{mock_config_instance.version}/conversations"
    )
    response = client.post(expected_path, params={"user_id": user_id})
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
    expected_response_data = {
        "conversation_id": expected_conversation_id,
        "user_id": expected_user_id,
    }
    assert response.json() == expected_response_data, (
        f"Expected response {expected_response_data}, got {response.json()}"
    )

    mock_conv_manager_instance.new_conversation.assert_called_once_with(user_id, False)


def test_add_conversation_message_by_id_endpoint(client: TestClient):
    """
    Test the /conversations/{conversation_id}/messages (POST) endpoint to add a message.

    Args:
        client (TestClient): The synchronous test client.
    """
    user_id = mock_conversation_object.user_id
    conversation_id = mock_conversation_object.conversation_id
    test_message = "Hello, agent! How are you doing today?"
    expected_agent_response = "Mocked agent response."

    expected_path = (
        f"/{mock_config_instance.service_name}/{mock_config_instance.version}/"
        f"conversations/{conversation_id}/messages"
    )

    request_body = {"message": test_message}
    response = client.post(
        expected_path,
        params={"user_id": user_id},
        json=request_body,
        headers={"Authorization": "Bearer dummy_token"},
    )
    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"

    response_data = response.json()
    assert "conversation" in response_data
    assert isinstance(response_data["conversation"], list)

    assert len(response_data["conversation"]) == 2
    assert response_data["conversation"][0]["content"] == test_message
    assert response_data["conversation"][1]["content"] == expected_agent_response
    assert response_data["conversation"][0]["recipient"] == "test_agent"
    assert response_data["conversation"][1]["sender"] == "test_agent"

    mock_conv_manager_instance.get_conversation.assert_called_with(user_id, conversation_id)
    mock_rec_chooser.choose_recipient.assert_called_once_with(
        test_message, mock_conversation_object, "Bearer dummy_token"
    )
    mock_agent_instance.invoke_api.assert_called_once()
    mock_conv_manager_instance.add_user_message.assert_called_once_with(
        mock_conversation_object, test_message, "test_agent"
    )
    mock_conv_manager_instance.add_agent_message.assert_called_once_with(
        mock_conversation_object, expected_agent_response, "test_agent"
    )
    mock_conv_manager_instance.get_last_response.assert_called_once_with(mock_conversation_object)


def test_get_conversation_by_id_endpoint(client: TestClient):
    """
    Test the /conversations/{conversation_id}/messages (GET) endpoint to get conversation history.
    This test will now retrieve the conversation history after messages have been added by
    test_add_conversation_message_by_id_endpoint (due to module-scoped fixture and test order).

    Args:
        client (TestClient): The synchronous test client.
    """
    user_id = mock_conversation_object.user_id
    conversation_id = mock_conversation_object.conversation_id

    expected_path = (
        f"/{mock_config_instance.service_name}/{mock_config_instance.version}/"
        f"conversations/{conversation_id}/messages"
    )
    expected_conversation_data = {}
    expected_response_data = {"conversation": expected_conversation_data}
    response = client.get(expected_path, params={"user_id": user_id})

    assert response.status_code == 200, f"Expected status code 200, got {response.status_code}"
    assert response.json() == expected_response_data, (
        f"Expected response {expected_response_data}, got {response.json()}"
    )

    mock_conv_manager_instance.get_conversation.assert_any_call(user_id, conversation_id)
