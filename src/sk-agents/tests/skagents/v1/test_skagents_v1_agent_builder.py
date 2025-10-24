from unittest.mock import MagicMock, patch

import pytest
from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.prompt_execution_settings import PromptExecutionSettings

from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.ska_types import ModelType
from sk_agents.skagents.kernel_builder import KernelBuilder
from sk_agents.skagents.v1.agent_builder import AgentBuilder
from sk_agents.skagents.v1.config import AgentConfig
from sk_agents.skagents.v1.sk_agent import SKAgent


@pytest.fixture
def mock_kernel_builder():
    """Create a mock KernelBuilder."""
    builder = MagicMock(spec=KernelBuilder)
    builder.build_kernel = MagicMock()
    builder.model_supports_structured_output = MagicMock()
    builder.get_model_type_for_name = MagicMock()
    return builder


@pytest.fixture
def agent_config():
    """Create a sample AgentConfig."""
    return AgentConfig(
        name="test-agent",
        model="gpt-4",
        system_prompt="You are a helpful assistant.",
        temperature=0.7,
        max_tokens=1000,
        plugins=["plugin1"],
        remote_plugins=["remote1"],
    )


@pytest.fixture
def minimal_agent_config():
    """Create a minimal AgentConfig without optional fields."""
    return AgentConfig(
        name="minimal-agent",
        model="gpt-3.5-turbo",
        system_prompt="Test prompt",
    )


class TestAgentBuilderInitialization:
    """Test AgentBuilder initialization."""

    def test_init_with_authorization(self, mock_kernel_builder):
        """Test __init__ with authorization parameter."""
        authorization = "Bearer token123"

        builder = AgentBuilder(mock_kernel_builder, authorization)

        assert builder.kernel_builder is mock_kernel_builder
        assert builder.authorization == authorization

    def test_init_without_authorization(self, mock_kernel_builder):
        """Test __init__ without authorization parameter."""
        builder = AgentBuilder(mock_kernel_builder)

        assert builder.kernel_builder is mock_kernel_builder
        assert builder.authorization is None


class TestBuildAgent:
    """Test build_agent method."""

    @patch("sk_agents.skagents.v1.agent_builder.ChatCompletionAgent")
    def test_build_agent_with_all_parameters(
        self, mock_agent_class, mock_kernel_builder, agent_config
    ):
        """Test build_agent with all optional parameters provided."""
        # Setup mocks
        mock_kernel = MagicMock(spec=Kernel)
        mock_settings = MagicMock(spec=PromptExecutionSettings)
        mock_settings.extension_data = {}
        mock_settings.service_id = "test-service-id"
        mock_kernel.get_prompt_execution_settings_from_service_id.return_value = mock_settings
        mock_kernel_builder.build_kernel.return_value = mock_kernel
        mock_kernel_builder.model_supports_structured_output.return_value = True
        mock_kernel_builder.get_model_type_for_name.return_value = ModelType.OPENAI

        mock_extra_data_collector = MagicMock(spec=ExtraDataCollector)
        output_type = "TestOutputType"

        mock_agent_instance = MagicMock(spec=ChatCompletionAgent)
        mock_agent_class.return_value = mock_agent_instance

        builder = AgentBuilder(mock_kernel_builder, authorization="Bearer token")

        # Execute
        with patch("sk_agents.skagents.v1.agent_builder.get_type_loader") as mock_get_type_loader:
            mock_type_loader = MagicMock()
            mock_type_loader.get_type.return_value = "MockedType"
            mock_get_type_loader.return_value = mock_type_loader

            result = builder.build_agent(agent_config, mock_extra_data_collector, output_type)

        # Verify kernel was built with correct parameters
        mock_kernel_builder.build_kernel.assert_called_once_with(
            agent_config.model,
            agent_config.name,
            agent_config.plugins,
            agent_config.remote_plugins,
            "Bearer token",
            mock_extra_data_collector,
        )

        # Verify settings were configured
        mock_kernel.get_prompt_execution_settings_from_service_id.assert_called_once_with(
            agent_config.name
        )
        assert mock_settings.function_choice_behavior is not None

        # Verify temperature and max_tokens were set
        assert mock_settings.extension_data["temperature"] == 0.7
        assert mock_settings.extension_data["max_tokens"] == 1000
        mock_settings.unpack_extension_data.assert_called_once()

        # Verify output type was set
        mock_type_loader.get_type.assert_called_once_with(output_type)
        assert mock_settings.response_format == "MockedType"

        # Verify agent was created
        mock_agent_class.assert_called_once()
        call_kwargs = mock_agent_class.call_args.kwargs
        assert call_kwargs["kernel"] is mock_kernel
        assert call_kwargs["name"] == agent_config.name
        assert call_kwargs["instructions"] == agent_config.system_prompt

        # Verify result
        assert isinstance(result, SKAgent)
        assert result.model_name == agent_config.model
        assert result.agent is mock_agent_instance
        assert result.model_attributes["model_type"] == ModelType.OPENAI
        assert result.model_attributes["so_supported"] is True

    @patch("sk_agents.skagents.v1.agent_builder.ChatCompletionAgent")
    def test_build_agent_minimal_config(
        self, mock_agent_class, mock_kernel_builder, minimal_agent_config
    ):
        """Test build_agent with minimal configuration (no temperature, max_tokens, etc)."""
        # Setup mocks
        mock_kernel = MagicMock(spec=Kernel)
        mock_settings = MagicMock(spec=PromptExecutionSettings)
        mock_settings.extension_data = {}
        mock_settings.service_id = "test-service-id"
        mock_kernel.get_prompt_execution_settings_from_service_id.return_value = mock_settings
        mock_kernel_builder.build_kernel.return_value = mock_kernel
        mock_kernel_builder.model_supports_structured_output.return_value = False
        mock_kernel_builder.get_model_type_for_name.return_value = ModelType.ANTHROPIC

        mock_agent_instance = MagicMock(spec=ChatCompletionAgent)
        mock_agent_class.return_value = mock_agent_instance

        builder = AgentBuilder(mock_kernel_builder)

        # Execute
        result = builder.build_agent(minimal_agent_config)

        # Verify kernel was built without extra data collector
        mock_kernel_builder.build_kernel.assert_called_once_with(
            minimal_agent_config.model,
            minimal_agent_config.name,
            minimal_agent_config.plugins,
            minimal_agent_config.remote_plugins,
            None,
            None,
        )

        # Verify extension_data was not set (since no temperature or max_tokens)
        mock_settings.unpack_extension_data.assert_not_called()

        # Verify response_format was not set (since so_supported is False)
        assert (
            not hasattr(mock_settings, "response_format") or mock_settings.response_format is None
        )

        # Verify result
        assert isinstance(result, SKAgent)
        assert result.model_name == minimal_agent_config.model
        assert result.model_attributes["model_type"] == ModelType.ANTHROPIC
        assert result.model_attributes["so_supported"] is False

    @patch("sk_agents.skagents.v1.agent_builder.ChatCompletionAgent")
    def test_build_agent_with_temperature_only(
        self, mock_agent_class, mock_kernel_builder, minimal_agent_config
    ):
        """Test build_agent with only temperature set."""
        minimal_agent_config.temperature = 0.5

        # Setup mocks
        mock_kernel = MagicMock(spec=Kernel)
        mock_settings = MagicMock(spec=PromptExecutionSettings)
        mock_settings.extension_data = {}
        mock_settings.service_id = "test-service-id"
        mock_kernel.get_prompt_execution_settings_from_service_id.return_value = mock_settings
        mock_kernel_builder.build_kernel.return_value = mock_kernel
        mock_kernel_builder.model_supports_structured_output.return_value = False
        mock_kernel_builder.get_model_type_for_name.return_value = ModelType.OPENAI

        mock_agent_instance = MagicMock(spec=ChatCompletionAgent)
        mock_agent_class.return_value = mock_agent_instance

        builder = AgentBuilder(mock_kernel_builder)

        # Execute
        result = builder.build_agent(minimal_agent_config)

        # Verify temperature was set but not max_tokens
        assert mock_settings.extension_data["temperature"] == 0.5
        assert "max_tokens" not in mock_settings.extension_data
        mock_settings.unpack_extension_data.assert_called_once()

        assert isinstance(result, SKAgent)

    @patch("sk_agents.skagents.v1.agent_builder.ChatCompletionAgent")
    def test_build_agent_with_max_tokens_only(
        self, mock_agent_class, mock_kernel_builder, minimal_agent_config
    ):
        """Test build_agent with only max_tokens set."""
        minimal_agent_config.max_tokens = 500

        # Setup mocks
        mock_kernel = MagicMock(spec=Kernel)
        mock_settings = MagicMock(spec=PromptExecutionSettings)
        mock_settings.extension_data = {}
        mock_settings.service_id = "test-service-id"
        mock_kernel.get_prompt_execution_settings_from_service_id.return_value = mock_settings
        mock_kernel_builder.build_kernel.return_value = mock_kernel
        mock_kernel_builder.model_supports_structured_output.return_value = False
        mock_kernel_builder.get_model_type_for_name.return_value = ModelType.OPENAI

        mock_agent_instance = MagicMock(spec=ChatCompletionAgent)
        mock_agent_class.return_value = mock_agent_instance

        builder = AgentBuilder(mock_kernel_builder)

        # Execute
        result = builder.build_agent(minimal_agent_config)

        # Verify max_tokens was set but not temperature
        assert "temperature" not in mock_settings.extension_data
        assert mock_settings.extension_data["max_tokens"] == 500
        mock_settings.unpack_extension_data.assert_called_once()

        assert isinstance(result, SKAgent)

    @patch("sk_agents.skagents.v1.agent_builder.ChatCompletionAgent")
    def test_build_agent_so_supported_without_output_type(
        self, mock_agent_class, mock_kernel_builder, minimal_agent_config
    ):
        """Test build_agent when SO is supported but no output_type provided."""
        # Setup mocks
        mock_kernel = MagicMock(spec=Kernel)
        mock_settings = MagicMock(spec=PromptExecutionSettings)
        mock_settings.extension_data = {}
        mock_settings.service_id = "test-service-id"
        mock_kernel.get_prompt_execution_settings_from_service_id.return_value = mock_settings
        mock_kernel_builder.build_kernel.return_value = mock_kernel
        mock_kernel_builder.model_supports_structured_output.return_value = True
        mock_kernel_builder.get_model_type_for_name.return_value = ModelType.OPENAI

        mock_agent_instance = MagicMock(spec=ChatCompletionAgent)
        mock_agent_class.return_value = mock_agent_instance

        builder = AgentBuilder(mock_kernel_builder)

        # Execute
        with patch("sk_agents.skagents.v1.agent_builder.get_type_loader") as mock_get_type_loader:
            result = builder.build_agent(minimal_agent_config, output_type=None)

            # Verify get_type_loader was not called
            mock_get_type_loader.assert_not_called()

        # Verify response_format was not set
        assert (
            not hasattr(mock_settings, "response_format") or mock_settings.response_format is None
        )

        assert isinstance(result, SKAgent)
        assert result.model_attributes["so_supported"] is True

    @patch("sk_agents.skagents.v1.agent_builder.ChatCompletionAgent")
    def test_build_agent_so_not_supported_with_output_type(
        self, mock_agent_class, mock_kernel_builder, minimal_agent_config
    ):
        """Test build_agent when SO is not supported even with output_type provided."""
        # Setup mocks
        mock_kernel = MagicMock(spec=Kernel)
        mock_settings = MagicMock(spec=PromptExecutionSettings)
        mock_settings.extension_data = {}
        mock_settings.service_id = "test-service-id"
        mock_kernel.get_prompt_execution_settings_from_service_id.return_value = mock_settings
        mock_kernel_builder.build_kernel.return_value = mock_kernel
        mock_kernel_builder.model_supports_structured_output.return_value = False
        mock_kernel_builder.get_model_type_for_name.return_value = ModelType.OPENAI

        mock_agent_instance = MagicMock(spec=ChatCompletionAgent)
        mock_agent_class.return_value = mock_agent_instance

        builder = AgentBuilder(mock_kernel_builder)

        # Execute
        with patch("sk_agents.skagents.v1.agent_builder.get_type_loader") as mock_get_type_loader:
            result = builder.build_agent(minimal_agent_config, output_type="SomeType")

            # Verify get_type_loader was not called (because so_supported is False)
            mock_get_type_loader.assert_not_called()

        assert isinstance(result, SKAgent)
        assert result.model_attributes["so_supported"] is False

    @patch("sk_agents.skagents.v1.agent_builder.ChatCompletionAgent")
    def test_build_agent_model_attributes(
        self, mock_agent_class, mock_kernel_builder, agent_config
    ):
        """Test that model_attributes are correctly set in the result."""
        # Setup mocks
        mock_kernel = MagicMock(spec=Kernel)
        mock_settings = MagicMock(spec=PromptExecutionSettings)
        mock_settings.extension_data = {}
        mock_settings.service_id = "test-service-id"
        mock_kernel.get_prompt_execution_settings_from_service_id.return_value = mock_settings
        mock_kernel_builder.build_kernel.return_value = mock_kernel
        mock_kernel_builder.model_supports_structured_output.return_value = True
        mock_kernel_builder.get_model_type_for_name.return_value = ModelType.GOOGLE

        mock_agent_instance = MagicMock(spec=ChatCompletionAgent)
        mock_agent_class.return_value = mock_agent_instance

        builder = AgentBuilder(mock_kernel_builder)

        # Execute
        result = builder.build_agent(agent_config)

        # Verify model_attributes
        assert result.model_attributes["model_type"] == ModelType.GOOGLE
        assert result.model_attributes["so_supported"] is True

    @patch("sk_agents.skagents.v1.agent_builder.ChatCompletionAgent")
    def test_build_agent_function_choice_behavior(
        self, mock_agent_class, mock_kernel_builder, minimal_agent_config
    ):
        """Test that function_choice_behavior is set correctly."""
        # Setup mocks
        mock_kernel = MagicMock(spec=Kernel)
        mock_settings = MagicMock(spec=PromptExecutionSettings)
        mock_settings.extension_data = {}
        mock_settings.service_id = "test-service-id"
        mock_kernel.get_prompt_execution_settings_from_service_id.return_value = mock_settings
        mock_kernel_builder.build_kernel.return_value = mock_kernel
        mock_kernel_builder.model_supports_structured_output.return_value = False
        mock_kernel_builder.get_model_type_for_name.return_value = ModelType.OPENAI

        mock_agent_instance = MagicMock(spec=ChatCompletionAgent)
        mock_agent_class.return_value = mock_agent_instance

        builder = AgentBuilder(mock_kernel_builder)

        # Execute
        result = builder.build_agent(minimal_agent_config)

        # Verify function_choice_behavior was set
        assert mock_settings.function_choice_behavior is not None

        assert isinstance(result, SKAgent)
