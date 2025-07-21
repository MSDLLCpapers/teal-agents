from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.types import AgentCard, AgentProvider, AgentSkill
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sk_agents.configs import TA_AGENT_BASE_URL, TA_PROVIDER_ORG, TA_PROVIDER_URL
from sk_agents.routes import Routes
from sk_agents.ska_types import BaseConfig, ConfigMetadata, ConfigSkill


def test_get_url_returns_correct_format():
    # Arrange
    mock_app_config = MagicMock()
    mock_app_config.get.return_value = "http://localhost"

    # Act
    url = Routes.get_url("my-agent", "1.0", mock_app_config)

    # Assert
    assert url == "http://localhost/my-agent/1.0/a2a"
    mock_app_config.get.assert_called_once_with(TA_AGENT_BASE_URL.env_name)


def test_get_url_raises_value_error_when_base_url_missing():
    # Arrange
    mock_app_config = MagicMock()
    mock_app_config.get.return_value = None

    # Act & Assert
    with pytest.raises(ValueError, match="Base URL is not provided in the app config."):
        Routes.get_url("my-agent", "1.0", mock_app_config)


def test_get_provider_returns_agent_provider():
    # Arrange
    mock_app_config = MagicMock()
    mock_app_config.get.side_effect = ["my-org", "https://provider.url"]

    # Act
    provider = Routes.get_provider(mock_app_config)

    # Assert
    assert isinstance(provider, AgentProvider)
    assert provider.organization == "my-org"
    assert provider.url == "https://provider.url"
    assert mock_app_config.get.call_count == 2
    mock_app_config.get.assert_any_call(TA_PROVIDER_ORG.env_name)
    mock_app_config.get.assert_any_call(TA_PROVIDER_URL.env_name)


def test_get_agent_card_success():
    # Arrange
    skill = ConfigSkill(
        id="skill1",
        name="Skill One",
        description="desc",
        tags=["tag1"],
        examples=["example1"],
        input_modes=["text"],
        output_modes=["text"],
    )
    metadata = ConfigMetadata(
        description="meta description", skills=[skill], documentation_url="http://docs.url"
    )
    config = BaseConfig(
        name="agent_name", version="1.0", metadata=metadata, apiVersion="v1", service_name="svc"
    )
    app_config = MagicMock()
    app_config.get.side_effect = lambda key: {
        TA_AGENT_BASE_URL.env_name: "http://base.url",
        TA_PROVIDER_ORG.env_name: "org",
        TA_PROVIDER_URL.env_name: "http://provider.url",
    }.get(key, None)

    # Act
    agent_card = Routes.get_agent_card(config, app_config)

    # Assert
    assert isinstance(agent_card, AgentCard)
    assert agent_card.name == config.name
    assert agent_card.version == str(config.version)
    assert agent_card.description == metadata.description
    assert agent_card.url == "http://base.url/agent_name/1.0/a2a"
    assert agent_card.provider.organization == "org"
    assert agent_card.provider.url == "http://provider.url"
    assert agent_card.documentationUrl == metadata.documentation_url
    assert agent_card.capabilities.streaming is True
    assert agent_card.defaultInputModes == ["text"]
    assert agent_card.defaultOutputModes == ["text"]
    assert len(agent_card.skills) == 1
    skill_out = agent_card.skills[0]
    assert isinstance(skill_out, AgentSkill)
    assert skill_out.id == skill.id
    assert skill_out.name == skill.name
    assert skill_out.description == skill.description
    assert skill_out.tags == skill.tags
    assert skill_out.examples == skill.examples
    assert skill_out.inputModes == skill.input_modes
    assert skill_out.outputModes == skill.output_modes


def test_get_agent_card_raises_without_metadata():
    # Arrange
    config = BaseConfig(
        name="agent_name", version="1.0", metadata=None, apiVersion="v1", service_name="svc"
    )
    app_config = MagicMock()

    # Act & Assert
    with pytest.raises(ValueError, match="Agent card metadata is not provided in the config."):
        Routes.get_agent_card(config, app_config)


def test_get_request_handler_returns_default_request_handler():
    config = BaseConfig(
        apiVersion="v1",
        name="agent_name",
        version="1.0",
    )
    app_config = MagicMock()
    chat_completion_builder = MagicMock()
    state_manager = MagicMock()
    task_store = MagicMock()

    with patch("sk_agents.routes.A2AAgentExecutor") as MockExecutor:
        mock_executor_instance = MagicMock()
        MockExecutor.return_value = mock_executor_instance

        handler = Routes.get_request_handler(
            config, app_config, chat_completion_builder, state_manager, task_store
        )

        # Ensure DefaultRequestHandler is returned
        assert isinstance(handler, DefaultRequestHandler)

        # The task_store passed correctly
        assert handler.task_store == task_store

        # The agent_executor is our mock instance
        assert handler.agent_executor == mock_executor_instance

        # Confirm A2AAgentExecutor was called with correct parameters
        MockExecutor.assert_called_once_with(
            config, app_config, chat_completion_builder, state_manager
        )


@pytest.fixture
def base_config():
    skill = ConfigSkill(
        id="skill1",
        name="Test Skill",
        description="Does test stuff",
        tags=["test", "example"],
        examples=["test input"],
        input_modes=["text"],
        output_modes=["text"],
    )
    metadata = ConfigMetadata(
        description="Test metadata", skills=[skill], documentation_url="https://example.com"
    )
    return BaseConfig(
        apiVersion="v1",
        version="1.0",
        name="Test Agent",
        service_name="test-service",
        description="An example agent",
        metadata=metadata,
        input_type="text",
        output_type="text",
        spec={"example_key": "example_value"},
    )


@pytest.fixture
def app_config():
    mock = MagicMock()
    mock.get.side_effect = lambda key: {
        "TA_AGENT_BASE_URL": "http://base.url",
        "TA_PROVIDER_ORG": "test_org",
        "TA_PROVIDER_URL": "http://provider.url",
    }.get(key)
    return mock


@pytest.fixture
def chat_completion_builder():
    return MagicMock()


@pytest.fixture
def task_store():
    return MagicMock()


@pytest.fixture
def state_manager():
    return MagicMock()


@patch("sk_agents.routes.A2AStarletteApplication")
@patch("sk_agents.routes.Routes.get_agent_card")
@patch("sk_agents.routes.Routes.get_request_handler")
def test_get_a2a_routes(
    mock_get_request_handler,
    mock_get_agent_card,
    mock_a2a_app,
    base_config,
    app_config,
    chat_completion_builder,
    task_store,
    state_manager,
):
    # Setup mocks return values
    mock_agent_card = MagicMock()
    mock_get_agent_card.return_value = mock_agent_card

    mock_request_handler = MagicMock()
    mock_get_request_handler.return_value = mock_request_handler

    mock_a2a_app_instance = MagicMock()
    mock_a2a_app.return_value = mock_a2a_app_instance

    router = Routes.get_a2a_routes(
        name=base_config.name,
        version=str(base_config.version),
        description=base_config.metadata.description,
        config=base_config,
        app_config=app_config,
        chat_completion_builder=chat_completion_builder,
        task_store=task_store,
        state_manager=state_manager,
    )

    # Validate router is created
    assert router is not None
    assert hasattr(router, "routes")

    # Check that A2AStarletteApplication was created with proper args
    mock_get_agent_card.assert_called_once_with(base_config, app_config)
    mock_get_request_handler.assert_called_once_with(
        base_config, app_config, chat_completion_builder, state_manager, task_store
    )
    mock_a2a_app.assert_called_once_with(
        agent_card=mock_agent_card,
        http_handler=mock_request_handler,
    )

    # Test that the router contains the expected route paths
    paths = [route.path for route in router.routes]
    assert "" in paths  # POST endpoint for handle_a2a
    assert "/.well-known/agent.json" in paths  # GET endpoint for agent card


@patch("sk_agents.routes.A2AStarletteApplication")
@patch("sk_agents.routes.Routes.get_agent_card")
@patch("sk_agents.routes.Routes.get_request_handler")
def test_handle_a2a_invocation(
    mock_get_request_handler,
    mock_get_agent_card,
    mock_a2a_app,
    base_config,
    app_config,
    chat_completion_builder,
    task_store,
    state_manager,
):
    # Setup mocks
    mock_agent_card = MagicMock()
    mock_get_agent_card.return_value = mock_agent_card

    mock_request_handler = MagicMock()
    mock_get_request_handler.return_value = mock_request_handler

    mock_a2a_app_instance = MagicMock()
    mock_a2a_app_instance._handle_requests = AsyncMock(return_value={"result": "success"})
    mock_a2a_app.return_value = mock_a2a_app_instance

    # Create the FastAPI router
    router = Routes.get_a2a_routes(
        name=base_config.name,
        version=str(base_config.version),
        description=base_config.metadata.description,
        config=base_config,
        app_config=app_config,
        chat_completion_builder=chat_completion_builder,
        task_store=task_store,
        state_manager=state_manager,
    )

    app = FastAPI()
    app.include_router(router, prefix="/a2a")

    client = TestClient(app)

    # Perform a POST to trigger handle_a2a
    response = client.post("/a2a", json={"some": "data"})

    # Assertions
    assert response.status_code == 200
    assert response.json() == {"result": "success"}
    mock_a2a_app_instance._handle_requests.assert_awaited_once()


@patch("sk_agents.routes.A2AStarletteApplication")
@patch("sk_agents.routes.Routes.get_agent_card")
@patch("sk_agents.routes.Routes.get_request_handler")
def test_handle_get_agent_card_route(
    mock_get_request_handler,
    mock_get_agent_card,
    mock_a2a_app,
    base_config,
    app_config,
    chat_completion_builder,
    task_store,
    state_manager,
):
    # Setup mock agent card
    mock_agent_card = MagicMock()
    mock_get_agent_card.return_value = mock_agent_card

    # Setup mock handler
    mock_handler = MagicMock()
    mock_get_request_handler.return_value = mock_handler

    # Mock a2a_app and its async _handle_get_agent_card method
    mock_a2a_app_instance = MagicMock()
    mock_a2a_app_instance._handle_get_agent_card = AsyncMock(return_value={"agent": "mocked_card"})
    mock_a2a_app.return_value = mock_a2a_app_instance

    # Build router
    router = Routes.get_a2a_routes(
        name=base_config.name,
        version=str(base_config.version),
        description=base_config.metadata.description,
        config=base_config,
        app_config=app_config,
        chat_completion_builder=chat_completion_builder,
        task_store=task_store,
        state_manager=state_manager,
    )

    # Mount router on FastAPI app
    app = FastAPI()
    app.include_router(router, prefix="/a2a")

    client = TestClient(app)

    # Send GET request to agent card route
    response = client.get("/a2a/.well-known/agent.json")

    # Assertions
    assert response.status_code == 200
    assert response.json() == {"agent": "mocked_card"}
    mock_a2a_app_instance._handle_get_agent_card.assert_awaited_once()
