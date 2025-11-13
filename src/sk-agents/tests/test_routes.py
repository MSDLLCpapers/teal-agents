from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.types import AgentCard, AgentProvider, AgentSkill
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from sk_agents.configs import TA_AGENT_BASE_URL, TA_PROVIDER_ORG, TA_PROVIDER_URL
from sk_agents.routes import Routes
from sk_agents.ska_types import BaseConfig, ConfigMetadata, ConfigSkill


class _TestInput(BaseModel):
    test_field: str = "test"


class _TestOutput(BaseModel):
    result: str


class MockAsyncIterator:
    """Reusable mock for async generators that yield responses."""

    def __init__(self, responses=None):
        self.responses = responses or ["response1", "response2"]
        self.index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.index < len(self.responses):
            response = self.responses[self.index]
            self.index += 1
            return response
        raise StopAsyncIteration


class MockAsyncIteratorWithError(MockAsyncIterator):
    """Mock async generator that raises exception after yielding some responses."""

    def __init__(self, responses=None, error_message="Stream error"):
        super().__init__(responses or ["response1"])
        self.error_message = error_message

    async def __anext__(self):
        if self.index < len(self.responses):
            response = self.responses[self.index]
            self.index += 1
            return response
        raise Exception(self.error_message)


class MockWebSocketGenerator(MockAsyncIterator):
    """Mock for WebSocket streaming with PartialResponse objects."""

    def __init__(self):
        from sk_agents.ska_types import PartialResponse

        super().__init__(
            [
                PartialResponse(output_partial="response1"),
                PartialResponse(output_partial="response2"),
            ]
        )


def setup_telemetry_mock(telemetry_enabled=True):
    """Create a telemetry mock with standard configuration."""
    mock_st = MagicMock()
    mock_st.telemetry_enabled.return_value = telemetry_enabled
    return mock_st


def setup_config_and_app():
    """Create standard config and app_config mocks."""
    config = MagicMock()
    config.apiVersion = "v1"
    app_config = MagicMock()
    return config, app_config


def setup_handler_with_stream(async_iterator=None):
    """Create a handler mock with invoke_stream method."""
    if async_iterator is None:
        async_iterator = MockAsyncIterator()

    mock_handler = MagicMock()
    mock_handler.invoke_stream = MagicMock(return_value=async_iterator)
    return mock_handler


def create_fastapi_test_client(router, prefix="/api"):
    """Create a FastAPI app with the router and return TestClient."""
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    return TestClient(app)


def setup_invoke_handler(response_data="test result", token_usage=None):
    """Create a handler mock for invoke endpoints."""
    from sk_agents.ska_types import InvokeResponse

    if token_usage is None:
        token_usage = {"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50}

    mock_handler = MagicMock()
    mock_response = InvokeResponse(
        token_usage=token_usage, extra_data=None, output_raw=response_data, output_pydantic=None
    )
    mock_handler.invoke = AsyncMock(return_value=mock_response)
    return mock_handler


def setup_stream_handler(responses=None, use_websocket=False):
    """Create a handler mock for streaming endpoints."""
    if responses is None:
        if use_websocket:
            return setup_handler_with_stream(MockWebSocketGenerator())
        else:
            return setup_handler_with_stream(MockAsyncIterator())
    return setup_handler_with_stream(MockAsyncIterator(responses))


def setup_error_stream_handler(error_message="Stream error"):
    """Create a handler mock that raises errors during streaming."""
    return setup_handler_with_stream(MockAsyncIteratorWithError(error_message=error_message))


def create_rest_routes_and_client(
    name="test-agent",
    version="v1",
    handler_name="skagents",
    config=None,
    app_config=None,
    description="Test description",
):
    """Create REST routes and test client in one call."""
    if config is None or app_config is None:
        config, app_config = setup_config_and_app()

    router = Routes.get_rest_routes(
        name=name,
        version=version,
        description=description,
        root_handler_name=handler_name,
        config=config,
        app_config=app_config,
        input_class=_TestInput,
        output_class=_TestOutput,
    )
    return router, create_fastapi_test_client(router)


def create_websocket_routes_and_client(
    name="test-agent", version="v1", handler_name="skagents", config=None, app_config=None
):
    """Create WebSocket routes and test client in one call."""
    if config is None or app_config is None:
        config, app_config = setup_config_and_app()

    router = Routes.get_websocket_routes(
        name=name,
        version=version,
        root_handler_name=handler_name,
        config=config,
        app_config=app_config,
        input_class=_TestInput,
    )
    return router, create_fastapi_test_client(router)


def test_get_url_returns_correct_format():
    mock_app_config = MagicMock()
    mock_app_config.get.return_value = "http://localhost"

    url = Routes.get_url("my-agent", "1.0", mock_app_config)

    assert url == "http://localhost/my-agent/1.0/a2a"
    mock_app_config.get.assert_called_once_with(TA_AGENT_BASE_URL.env_name)


def test_get_url_raises_value_error_when_base_url_missing():
    mock_app_config = MagicMock()
    mock_app_config.get.return_value = None

    with pytest.raises(ValueError, match="Base URL is not provided in the app config."):
        Routes.get_url("my-agent", "1.0", mock_app_config)


def test_get_provider_returns_agent_provider():
    mock_app_config = MagicMock()
    mock_app_config.get.side_effect = ["my-org", "https://provider.url"]

    provider = Routes.get_provider(mock_app_config)

    assert isinstance(provider, AgentProvider)
    assert provider.organization == "my-org"
    assert provider.url == "https://provider.url"
    assert mock_app_config.get.call_count == 2
    mock_app_config.get.assert_any_call(TA_PROVIDER_ORG.env_name)
    mock_app_config.get.assert_any_call(TA_PROVIDER_URL.env_name)


def test_get_agent_card_success():
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

    agent_card = Routes.get_agent_card(config, app_config)

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
    config = BaseConfig(
        name="agent_name", version="1.0", metadata=None, apiVersion="v1", service_name="svc"
    )
    app_config = MagicMock()

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

    assert response.status_code == 200
    assert response.json() == {"agent": "mocked_card"}
    mock_a2a_app_instance._handle_get_agent_card.assert_awaited_once()


# Test helper methods
@patch("sk_agents.routes.ChatCompletionBuilder")
def test_create_chat_completions_builder(mock_builder_class):
    """Test _create_chat_completions_builder helper method."""
    mock_app_config = MagicMock()
    mock_builder = MagicMock()
    mock_builder_class.return_value = mock_builder

    result = Routes._create_chat_completions_builder(mock_app_config)

    mock_builder_class.assert_called_once_with(mock_app_config)
    assert result == mock_builder


@patch("sk_agents.routes.RemotePluginLoader")
@patch("sk_agents.routes.RemotePluginCatalog")
def test_create_remote_plugin_loader(mock_catalog_class, mock_loader_class):
    """Test _create_remote_plugin_loader helper method."""
    mock_app_config = MagicMock()
    mock_catalog = MagicMock()
    mock_loader = MagicMock()
    mock_catalog_class.return_value = mock_catalog
    mock_loader_class.return_value = mock_loader

    result = Routes._create_remote_plugin_loader(mock_app_config)

    mock_catalog_class.assert_called_once_with(mock_app_config)
    mock_loader_class.assert_called_once_with(mock_catalog)
    assert result == mock_loader


@patch("sk_agents.routes.KernelBuilder")
@patch.object(Routes, "_create_remote_plugin_loader")
@patch.object(Routes, "_create_chat_completions_builder")
def test_create_kernel_builder(mock_chat_builder, mock_plugin_loader, mock_kernel_builder_class):
    """Test _create_kernel_builder helper method."""
    mock_app_config = MagicMock()
    authorization = "test_auth"
    mock_chat_completions = MagicMock()
    mock_remote_plugin_loader = MagicMock()
    mock_kernel_builder = MagicMock()

    mock_chat_builder.return_value = mock_chat_completions
    mock_plugin_loader.return_value = mock_remote_plugin_loader
    mock_kernel_builder_class.return_value = mock_kernel_builder

    result = Routes._create_kernel_builder(mock_app_config, authorization)

    mock_chat_builder.assert_called_once_with(mock_app_config)
    mock_plugin_loader.assert_called_once_with(mock_app_config)
    mock_kernel_builder_class.assert_called_once_with(
        mock_chat_completions, mock_remote_plugin_loader, mock_app_config, authorization
    )
    assert result == mock_kernel_builder


@patch("sk_agents.routes.AgentBuilder")
@patch.object(Routes, "_create_kernel_builder")
def test_create_agent_builder(mock_kernel_builder, mock_agent_builder_class):
    """Test _create_agent_builder helper method."""
    mock_app_config = MagicMock()
    authorization = "test_auth"
    mock_kernel_builder_instance = MagicMock()
    mock_agent_builder = MagicMock()

    mock_kernel_builder.return_value = mock_kernel_builder_instance
    mock_agent_builder_class.return_value = mock_agent_builder

    result = Routes._create_agent_builder(mock_app_config, authorization)

    mock_kernel_builder.assert_called_once_with(mock_app_config, authorization)
    mock_agent_builder_class.assert_called_once_with(mock_kernel_builder_instance, authorization)
    assert result == mock_agent_builder


@patch("sk_agents.routes.TealAgentsV1Alpha1Handler")
@patch.object(Routes, "_create_agent_builder")
def test_get_task_handler(mock_agent_builder, mock_handler_class):
    """Test get_task_handler method."""
    config = MagicMock()
    app_config = MagicMock()
    authorization = "test_auth"
    state_manager = MagicMock()
    mcp_discovery_manager = MagicMock()

    mock_agent_builder_instance = MagicMock()
    mock_handler = MagicMock()

    mock_agent_builder.return_value = mock_agent_builder_instance
    mock_handler_class.return_value = mock_handler

    result = Routes.get_task_handler(config, app_config, authorization, state_manager, mcp_discovery_manager)

    mock_agent_builder.assert_called_once_with(app_config, authorization)
    mock_handler_class.assert_called_once_with(
        config, app_config, mock_agent_builder_instance, state_manager, mcp_discovery_manager
    )
    assert result == mock_handler


@patch("sk_agents.routes.skagents_handle")
@patch("sk_agents.routes.get_telemetry")
@patch("sk_agents.routes.extract")
def test_get_rest_routes_skagents_invoke(mock_extract, mock_get_telemetry, mock_skagents_handle):
    """Test get_rest_routes with skagents handler - invoke endpoint."""
    mock_get_telemetry.return_value = setup_telemetry_mock()
    mock_extract.return_value = {}

    mock_handler = setup_invoke_handler("test result")
    mock_skagents_handle.return_value = mock_handler

    config, app_config = setup_config_and_app()
    router, client = create_rest_routes_and_client(
        handler_name="skagents", config=config, app_config=app_config
    )

    response = client.post("/api", json={"test_field": "test_value"})

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["token_usage"]["total_tokens"] == 100
    assert response_data["output_raw"] == "test result"
    mock_handler.invoke.assert_awaited_once()


@patch("sk_agents.routes.skagents_handle")
@patch("sk_agents.routes.get_telemetry")
@patch("sk_agents.routes.extract")
@patch("sk_agents.routes.get_sse_event_for_response")
def test_get_rest_routes_skagents_sse(
    mock_sse_event, mock_extract, mock_get_telemetry, mock_skagents_handle
):
    """Test get_rest_routes with skagents handler - SSE endpoint."""
    mock_get_telemetry.return_value = setup_telemetry_mock(telemetry_enabled=False)
    mock_extract.return_value = {}
    mock_sse_event.return_value = "data: test event\n\n"

    mock_handler = setup_stream_handler([{"content": "response1"}, {"content": "response2"}])
    mock_skagents_handle.return_value = mock_handler

    config, app_config = setup_config_and_app()
    router, client = create_rest_routes_and_client(
        handler_name="skagents", config=config, app_config=app_config
    )

    response = client.post("/api/sse", json={"test_field": "test_value"})

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


@patch("sk_agents.routes.get_telemetry")
def test_get_rest_routes_unknown_handler(mock_get_telemetry):
    """Test get_rest_routes with unknown handler raises ValueError."""
    mock_get_telemetry.return_value = setup_telemetry_mock()

    config, app_config = setup_config_and_app()
    config.apiVersion = "unknown"

    router, client = create_rest_routes_and_client(
        handler_name="unknown", config=config, app_config=app_config
    )

    # Test that the ValueError is raised during request processing
    try:
        client.post("/api", json={"test_field": "test"})
        raise AssertionError("Expected ValueError to be raised")
    except ValueError as e:
        assert "Unknown apiVersion: unknown" in str(e)


@patch("sk_agents.routes.get_telemetry")
def test_get_rest_routes_sse_unknown_handler(mock_get_telemetry):
    """Test get_rest_routes SSE endpoint with unknown handler raises ValueError."""
    mock_get_telemetry.return_value = setup_telemetry_mock()

    config, app_config = setup_config_and_app()

    router, client = create_rest_routes_and_client(
        handler_name="unknown_handler", config=config, app_config=app_config
    )

    # Test that the ValueError is raised during SSE stream processing
    try:
        response = client.post("/api/sse", json={"test_field": "test"})
        # Need to consume the stream to trigger the generator
        for _ in response.iter_content():
            pass
        raise AssertionError("Expected ValueError to be raised")
    except ValueError as e:
        assert "Unknown apiVersion: v1" in str(e)


@patch("sk_agents.routes.skagents_handle")
@patch("sk_agents.routes.get_telemetry")
@patch("sk_agents.routes.extract")
def test_get_websocket_routes_skagents(mock_extract, mock_get_telemetry, mock_skagents_handle):
    """Test get_websocket_routes with skagents handler."""
    mock_get_telemetry.return_value = setup_telemetry_mock()
    mock_extract.return_value = {}

    mock_handler = setup_stream_handler(use_websocket=True)
    mock_skagents_handle.return_value = mock_handler

    config, app_config = setup_config_and_app()
    router, client = create_websocket_routes_and_client(
        handler_name="skagents", config=config, app_config=app_config
    )

    # Test that the router is created with WebSocket route
    assert router is not None
    websocket_routes = [r for r in router.routes if hasattr(r, "path") and r.path == "/stream"]
    assert len(websocket_routes) == 1

    # Verify mocks are only called during WebSocket execution
    mock_get_telemetry.assert_not_called()
    mock_skagents_handle.assert_not_called()


@pytest.mark.asyncio
@patch("sk_agents.routes.skagents_handle")
@patch("sk_agents.routes.get_telemetry")
@patch("sk_agents.routes.extract")
async def test_websocket_route_execution(mock_extract, mock_get_telemetry, mock_skagents_handle):
    """Test WebSocket route execution with mocks."""
    from fastapi import WebSocket

    mock_get_telemetry.return_value = setup_telemetry_mock()
    mock_extract.return_value = {}
    mock_handler = setup_stream_handler(use_websocket=True)
    mock_skagents_handle.return_value = mock_handler

    # Mock WebSocket
    mock_websocket = MagicMock(spec=WebSocket)
    mock_websocket.headers = {"authorization": "Bearer test"}
    mock_websocket.accept = AsyncMock()
    mock_websocket.receive_json = AsyncMock(return_value={"test_field": "test"})
    mock_websocket.send_text = AsyncMock()
    mock_websocket.close = AsyncMock()

    config, app_config = setup_config_and_app()
    router, _ = create_websocket_routes_and_client(config=config, app_config=app_config)

    # Find and call the WebSocket route function
    websocket_route = next(r for r in router.routes if hasattr(r, "path") and r.path == "/stream")
    await websocket_route.endpoint(mock_websocket)

    # Verify the expected calls were made
    mock_websocket.accept.assert_called_once()
    mock_websocket.receive_json.assert_called_once()
    mock_skagents_handle.assert_called_once()
    mock_websocket.close.assert_called_once()


@pytest.mark.asyncio
@patch("sk_agents.routes.get_telemetry")
async def test_websocket_route_unknown_handler(mock_get_telemetry):
    """Test WebSocket route with unknown handler raises ValueError."""
    # Setup mocks
    mock_st = MagicMock()
    mock_st.telemetry_enabled.return_value = True
    mock_get_telemetry.return_value = mock_st

    # Mock WebSocket
    from fastapi import WebSocket

    mock_websocket = MagicMock(spec=WebSocket)
    mock_websocket.headers = {"authorization": "Bearer test"}
    mock_websocket.accept = AsyncMock()
    mock_websocket.receive_json = AsyncMock(return_value={"test_field": "test"})

    config = MagicMock()
    config.apiVersion = "unknown"
    app_config = MagicMock()

    from pydantic import BaseModel

    class TestInput(BaseModel):
        test_field: str = "test"

    router = Routes.get_websocket_routes(
        name="test-agent",
        version="v1",
        root_handler_name="unknown",
        config=config,
        app_config=app_config,
        input_class=TestInput,
    )

    # Find the WebSocket route
    websocket_route = None
    for route in router.routes:
        if hasattr(route, "path") and route.path == "/stream":
            websocket_route = route
            break

    assert websocket_route is not None

    # Call the WebSocket endpoint function - should raise ValueError
    with pytest.raises(ValueError, match="Unknown apiVersion"):
        await websocket_route.endpoint(mock_websocket)


@pytest.mark.asyncio
@patch("sk_agents.routes.get_telemetry")
@patch("sk_agents.routes.extract")
async def test_websocket_route_disconnect(mock_extract, mock_get_telemetry):
    """Test WebSocket route handles WebSocketDisconnect."""
    from starlette.websockets import WebSocketDisconnect

    # Setup mocks
    mock_st = MagicMock()
    mock_st.telemetry_enabled.return_value = True
    mock_get_telemetry.return_value = mock_st
    mock_extract.return_value = {}

    # Mock WebSocket that raises disconnect
    from fastapi import WebSocket

    mock_websocket = MagicMock(spec=WebSocket)
    mock_websocket.headers = {"authorization": "Bearer test"}
    mock_websocket.accept = AsyncMock()
    mock_websocket.receive_json = AsyncMock(side_effect=WebSocketDisconnect())

    config = MagicMock()
    config.apiVersion = "v1"
    app_config = MagicMock()

    from pydantic import BaseModel

    class TestInput(BaseModel):
        test_field: str = "test"

    router = Routes.get_websocket_routes(
        name="test-agent",
        version="v1",
        root_handler_name="skagents",
        config=config,
        app_config=app_config,
        input_class=TestInput,
    )

    # Find the WebSocket route
    websocket_route = None
    for route in router.routes:
        if hasattr(route, "path") and route.path == "/stream":
            websocket_route = route
            break

    assert websocket_route is not None

    # Call the WebSocket endpoint - should handle WebSocketDisconnect gracefully
    await websocket_route.endpoint(mock_websocket)

    # Verify WebSocket accept was called
    mock_websocket.accept.assert_called_once()


@patch("sk_agents.routes.Routes.get_task_handler")
def test_get_stateful_routes_success(mock_get_task_handler):
    """Test get_stateful_routes successful chat endpoint."""
    from sk_agents.tealagents.models import TealAgentsResponse

    # Setup mocks
    mock_teal_handler = MagicMock()
    mock_response = TealAgentsResponse(
        task_id="task123",
        session_id="session123",
        request_id="request123",
        output="Test response",
        token_usage={"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50},
    )
    mock_teal_handler.invoke = AsyncMock(return_value=mock_response)
    mock_get_task_handler.return_value = mock_teal_handler

    mock_authorizer = MagicMock()
    mock_authorizer.authorize_request = AsyncMock(return_value="user123")

    config = MagicMock()
    app_config = MagicMock()
    state_manager = MagicMock()
    auth_storage_manager = MagicMock()
    mcp_discovery_manager = MagicMock()

    from sk_agents.tealagents.models import UserMessage

    # Get the router
    router = Routes.get_stateful_routes(
        name="test-agent",
        version="v1",
        description="Test description",
        config=config,
        app_config=app_config,
        state_manager=state_manager,
        authorizer=mock_authorizer,
        auth_storage_manager=auth_storage_manager,
        mcp_discovery_manager=mcp_discovery_manager,
        input_class=UserMessage,
    )

    # Mount router in FastAPI app and test
    app = FastAPI()
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    response = client.post(
        "/api",
        json={
            "items": [],
            "session_id": "session123",
            "user_id": "user123",
            "request_id": "req123",
        },
        headers={"authorization": "Bearer token123"},
    )

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["session_id"] == "session123"
    assert response_data["task_id"] == "task123"
    assert response_data["request_id"] == "request123"
    assert response_data["status"] == "Completed"


@patch("sk_agents.routes.Routes.get_task_handler")
def test_get_stateful_routes_hitl_response(mock_get_task_handler):
    """Test get_stateful_routes with HitlResponse (paused status)."""
    # Setup mocks
    from sk_agents.tealagents.models import HitlResponse

    mock_teal_handler = MagicMock()
    mock_response = HitlResponse(
        session_id="session123",
        task_id="task123",
        request_id="request123",
        message="Approval required",
        approval_url="https://example.com/approve",
        rejection_url="https://example.com/reject",
        tool_calls=[{"function": "test_function", "args": {}}],
    )
    mock_teal_handler.invoke = AsyncMock(return_value=mock_response)
    mock_get_task_handler.return_value = mock_teal_handler

    mock_authorizer = MagicMock()
    mock_authorizer.authorize_request = AsyncMock(return_value="user123")

    config = MagicMock()
    app_config = MagicMock()
    state_manager = MagicMock()
    auth_storage_manager = MagicMock()
    mcp_discovery_manager = MagicMock()

    from sk_agents.tealagents.models import UserMessage

    # Get the router
    router = Routes.get_stateful_routes(
        name="test-agent",
        version="v1",
        description="Test description",
        config=config,
        app_config=app_config,
        state_manager=state_manager,
        authorizer=mock_authorizer,
        auth_storage_manager=auth_storage_manager,
        mcp_discovery_manager=mcp_discovery_manager,
        input_class=UserMessage,
    )

    # Mount router in FastAPI app and test
    app = FastAPI()
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    response = client.post(
        "/api",
        json={
            "items": [],
            "session_id": "session123",
            "user_id": "user123",
            "request_id": "req123",
        },
        headers={"authorization": "Bearer token123"},
    )

    assert response.status_code == 200
    response_data = response.json()
    assert response_data["status"] == "Paused"


def test_get_stateful_routes_unauthorized():
    """Test get_stateful_routes with unauthorized access."""
    mock_authorizer = MagicMock()
    mock_authorizer.authorize_request = AsyncMock(return_value=None)

    config = MagicMock()
    app_config = MagicMock()
    state_manager = MagicMock()
    auth_storage_manager = MagicMock()
    mcp_discovery_manager = MagicMock()

    from sk_agents.tealagents.models import UserMessage

    # Get the router
    router = Routes.get_stateful_routes(
        name="test-agent",
        version="v1",
        description="Test description",
        config=config,
        app_config=app_config,
        state_manager=state_manager,
        authorizer=mock_authorizer,
        auth_storage_manager=auth_storage_manager,
        mcp_discovery_manager=mcp_discovery_manager,
        input_class=UserMessage,
    )

    # Mount router in FastAPI app and test
    app = FastAPI()
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    response = client.post(
        "/api",
        json={
            "items": [],
            "session_id": "session123",
            "user_id": "user123",
            "request_id": "req123",
        },
        headers={"authorization": "Bearer invalid_token"},
    )

    assert response.status_code == 401


@patch("sk_agents.routes.Routes.get_task_handler")
def test_get_resume_routes_success(mock_get_task_handler):
    """Test get_resume_routes successful resume endpoint."""
    # Setup mocks
    mock_teal_handler = MagicMock()
    mock_response = MagicMock()
    mock_teal_handler.resume_task = AsyncMock(return_value=mock_response)
    mock_get_task_handler.return_value = mock_teal_handler

    config = MagicMock()
    app_config = MagicMock()
    state_manager = MagicMock()
    mcp_discovery_manager = MagicMock()

    # Get the router
    router = Routes.get_resume_routes(config, app_config, state_manager, mcp_discovery_manager)

    # Mount router in FastAPI app and test
    app = FastAPI()
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    response = client.post(
        "/api/tealagents/v1alpha1/resume/request123",
        json={"action": "approve"},
        headers={"authorization": "Bearer token123"},
    )

    assert response.status_code == 200
    # Verify the call was made with correct parameters
    mock_teal_handler.resume_task.assert_awaited_once()
    call_args = mock_teal_handler.resume_task.call_args
    assert call_args[0][0] == "Bearer token123"  # authorization
    assert call_args[0][1] == "request123"  # request_id
    assert call_args[0][2].action == "approve"  # ResumeRequest object
    assert call_args[1]["stream"] is False


@patch("sk_agents.routes.Routes.get_task_handler")
@patch("sk_agents.routes.get_sse_event_for_response")
def test_get_resume_routes_sse_success(mock_sse_event, mock_get_task_handler):
    """Test get_resume_routes SSE endpoint."""

    # Setup mocks
    class MockAsyncIterator:
        def __init__(self):
            self.items = [{"content": "response1"}, {"content": "response2"}]
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.index < len(self.items):
                item = self.items[self.index]
                self.index += 1
                return item
            raise StopAsyncIteration

    mock_teal_handler = MagicMock()

    def mock_side_effect(*args, **kwargs):
        if kwargs.get("stream"):
            return MockAsyncIterator()
        else:
            return AsyncMock(return_value={"result": "test"})()

    mock_teal_handler.resume_task = MagicMock(side_effect=mock_side_effect)
    mock_get_task_handler.return_value = mock_teal_handler
    mock_sse_event.return_value = "data: test event\n\n"

    config = MagicMock()
    app_config = MagicMock()
    state_manager = MagicMock()
    mcp_discovery_manager = MagicMock()

    # Get the router
    router = Routes.get_resume_routes(config, app_config, state_manager, mcp_discovery_manager)

    # Mount router in FastAPI app and test
    app = FastAPI()
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    response = client.post(
        "/api/tealagents/v1alpha1/resume/request123/sse",
        json={"action": "approve"},
        headers={"authorization": "Bearer token123"},
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


@patch("sk_agents.routes.Routes.get_task_handler")
def test_get_resume_routes_exception(mock_get_task_handler):
    """Test get_resume_routes exception handling."""
    # Setup mocks
    mock_teal_handler = MagicMock()
    mock_teal_handler.resume_task = AsyncMock(side_effect=Exception("Test error"))
    mock_get_task_handler.return_value = mock_teal_handler

    config = MagicMock()
    app_config = MagicMock()
    state_manager = MagicMock()
    mcp_discovery_manager = MagicMock()

    # Get the router
    router = Routes.get_resume_routes(config, app_config, state_manager, mcp_discovery_manager)

    # Mount router in FastAPI app and test
    app = FastAPI()
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    response = client.post(
        "/api/tealagents/v1alpha1/resume/request123",
        json={"action": "approve"},
        headers={"authorization": "Bearer token123"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal Server Error"


@patch("sk_agents.routes.Routes.get_task_handler")
@patch("sk_agents.routes.get_sse_event_for_response")
def test_get_resume_routes_sse_exception(mock_sse_event, mock_get_task_handler):
    """Test get_resume_routes SSE endpoint exception handling."""

    # Setup mocks
    class MockAsyncIteratorWithError:
        def __init__(self):
            self.items = [{"content": "response1"}]
            self.index = 0

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self.index < len(self.items):
                item = self.items[self.index]
                self.index += 1
                return item
            raise Exception("Stream error")

    mock_teal_handler = MagicMock()

    def mock_side_effect(*args, **kwargs):
        if kwargs.get("stream"):
            return MockAsyncIteratorWithError()
        else:
            return AsyncMock(return_value={"result": "test"})()

    mock_teal_handler.resume_task = MagicMock(side_effect=mock_side_effect)
    mock_get_task_handler.return_value = mock_teal_handler
    mock_sse_event.return_value = "data: test event\n\n"

    config = MagicMock()
    app_config = MagicMock()
    state_manager = MagicMock()
    mcp_discovery_manager = MagicMock()

    # Get the router
    router = Routes.get_resume_routes(config, app_config, state_manager, mcp_discovery_manager)

    # Mount router in FastAPI app and test
    app = FastAPI()
    app.include_router(router, prefix="/api")

    client = TestClient(app)
    # Should raise RuntimeError because the response has already started
    # when the exception occurs in the SSE stream
    with pytest.raises(RuntimeError, match="response already started"):
        client.post(
            "/api/tealagents/v1alpha1/resume/request123/sse",
            json={"action": "approve"},
            headers={"authorization": "Bearer token123"},
        )


@patch("sk_agents.routes.skagents_handle")
@patch("sk_agents.routes.get_telemetry")
@patch("sk_agents.routes.extract")
def test_get_websocket_routes_unknown_handler(
    mock_extract, mock_get_telemetry, mock_skagents_handle
):
    """Test get_websocket_routes with unknown handler."""
    # Setup mocks
    mock_st = MagicMock()
    mock_st.telemetry_enabled.return_value = True
    mock_get_telemetry.return_value = mock_st
    mock_extract.return_value = {}

    config = MagicMock()
    config.apiVersion = "unknown"
    app_config = MagicMock()

    from pydantic import BaseModel

    class TestInput(BaseModel):
        test_field: str = "test"

    class TestOutput(BaseModel):
        result: str

    # Get the router
    router = Routes.get_websocket_routes(
        name="test-agent",
        version="v1",
        root_handler_name="unknown",
        config=config,
        app_config=app_config,
        input_class=TestInput,
    )

    # Test WebSocket routing - should still create router even with unknown handler
    # The error will occur during actual WebSocket execution
    assert router is not None


@pytest.mark.parametrize(
    "handler_name,should_succeed",
    [
        ("skagents", True),
        ("unknown", False),
    ],
)
def test_websocket_error_scenarios(handler_name, should_succeed):
    """Test WebSocket route creation with various handlers."""
    config, app_config = setup_config_and_app()
    if not should_succeed:
        config.apiVersion = "unknown"  # Force error scenario

    router, _ = create_websocket_routes_and_client(
        handler_name=handler_name, config=config, app_config=app_config
    )

    # Router creation should always succeed; errors occur during execution
    assert router is not None
    websocket_routes = [r for r in router.routes if hasattr(r, "path") and r.path == "/stream"]
    assert len(websocket_routes) == 1
