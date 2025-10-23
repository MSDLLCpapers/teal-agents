from unittest.mock import MagicMock, patch

import pytest

from sk_agents.chat_completion.custom.example_custom_chat_completion_factory import (
    ExampleCustomChatCompletionFactory,
)
from sk_agents.configs import TA_API_KEY
from sk_agents.ska_types import ModelType


@pytest.fixture
def mock_app_config():
    """Create a mock app config for testing."""
    config = MagicMock()
    config.get.side_effect = lambda key: {
        TA_API_KEY.env_name: "test_api_key_12345",
        ExampleCustomChatCompletionFactory.TA_BASE_URL.env_name: "https://test-endpoint.example.com",
        ExampleCustomChatCompletionFactory.TA_API_VERSION.env_name: "2024-10-21",
    }.get(key, None)
    return config


@pytest.fixture
def factory(mock_app_config):
    """Create an ExampleCustomChatCompletionFactory instance."""
    return ExampleCustomChatCompletionFactory(mock_app_config)


class TestFactoryInitialization:
    """Test factory initialization and configuration."""

    def test_factory_inherits_from_chat_completion_factory(self, factory):
        """Test that ExampleCustomChatCompletionFactory inherits from ChatCompletionFactory."""
        from sk_agents.ska_types import ChatCompletionFactory

        assert isinstance(factory, ChatCompletionFactory)

    def test_factory_stores_app_config(self, mock_app_config):
        """Test that factory stores the app_config."""
        factory = ExampleCustomChatCompletionFactory(mock_app_config)
        assert factory.app_config is mock_app_config

    def test_factory_stores_api_key(self, factory):
        """Test that factory stores the API key from config."""
        assert factory.api_key == "test_api_key_12345"

    def test_factory_stores_url_base(self, factory):
        """Test that factory stores the base URL from config."""
        assert factory.url_base == "https://test-endpoint.example.com"

    def test_factory_stores_api_version(self, factory):
        """Test that factory stores the API version from config."""
        assert factory.api_version == "2024-10-21"

    def test_openai_models_list_contains_expected_models(self):
        """Test that the OPENAI_MODELS list contains expected models."""
        assert "gpt-35-turbo-1106" in ExampleCustomChatCompletionFactory._OPENAI_MODELS
        assert "gpt-4o-2024-05-13" in ExampleCustomChatCompletionFactory._OPENAI_MODELS
        assert len(ExampleCustomChatCompletionFactory._OPENAI_MODELS) == 6

    def test_anthropic_models_list_contains_expected_models(self):
        """Test that the ANTHROPIC_MODELS list contains expected models."""
        assert "claude-3-5-sonnet-20240620" in ExampleCustomChatCompletionFactory._ANTHROPIC_MODELS
        assert "claude-3-haiku-20240307" in ExampleCustomChatCompletionFactory._ANTHROPIC_MODELS
        assert len(ExampleCustomChatCompletionFactory._ANTHROPIC_MODELS) == 2

    def test_google_models_list_contains_expected_models(self):
        """Test that the GOOGLE_MODELS list contains expected models."""
        assert "gemini-2-5-pro-preview-03-25" in ExampleCustomChatCompletionFactory._GOOGLE_MODELS
        assert "gemini-2-0-flash" in ExampleCustomChatCompletionFactory._GOOGLE_MODELS
        assert len(ExampleCustomChatCompletionFactory._GOOGLE_MODELS) == 4


class TestGetConfigs:
    """Test get_configs static method."""

    def test_get_configs_returns_list(self):
        """Test that get_configs returns a list."""
        result = ExampleCustomChatCompletionFactory.get_configs()
        assert isinstance(result, list)

    def test_get_configs_contains_ta_base_url(self):
        """Test that get_configs includes TA_BASE_URL config."""
        configs = ExampleCustomChatCompletionFactory.get_configs()
        assert ExampleCustomChatCompletionFactory.TA_BASE_URL in configs

    def test_get_configs_contains_ta_api_version(self):
        """Test that get_configs includes TA_API_VERSION config."""
        configs = ExampleCustomChatCompletionFactory.get_configs()
        assert ExampleCustomChatCompletionFactory.TA_API_VERSION in configs

    def test_get_configs_has_correct_count(self):
        """Test that get_configs returns exactly 2 configs."""
        configs = ExampleCustomChatCompletionFactory.get_configs()
        assert len(configs) == 2


class TestGetChatCompletionForModelName:
    """Test get_chat_completion_for_model_name method."""

    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AzureChatCompletion"
    )
    def test_openai_model_creates_azure_completion(self, mock_azure_class, factory):
        """Test that OpenAI model creates an AzureChatCompletion instance."""
        mock_instance = MagicMock()
        mock_azure_class.return_value = mock_instance

        result = factory.get_chat_completion_for_model_name("gpt-4o-2024-05-13", "test_service")

        # Verify AzureChatCompletion was called with correct parameters
        mock_azure_class.assert_called_once_with(
            service_id="test_service",
            deployment_name="gpt-4o-2024-05-13",
            api_key="test_api_key_12345",
            base_url="https://test-endpoint.example.com/openai",
            api_version="2024-10-21",
        )
        assert result == mock_instance

    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AzureChatCompletion"
    )
    def test_gpt_35_turbo_model_creates_azure_completion(self, mock_azure_class, factory):
        """Test that GPT-3.5 Turbo model creates an AzureChatCompletion instance."""
        mock_instance = MagicMock()
        mock_azure_class.return_value = mock_instance

        result = factory.get_chat_completion_for_model_name("gpt-35-turbo-1106", "turbo_service")

        mock_azure_class.assert_called_once()
        call_kwargs = mock_azure_class.call_args.kwargs
        assert call_kwargs["deployment_name"] == "gpt-35-turbo-1106"
        assert result == mock_instance

    @patch("sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AsyncAnthropic")
    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AnthropicChatCompletion"
    )
    def test_anthropic_model_creates_anthropic_completion(
        self, mock_anthropic_class, mock_async_anthropic_class, factory
    ):
        """Test that Anthropic model creates an AnthropicChatCompletion instance."""
        mock_instance = MagicMock()
        mock_anthropic_class.return_value = mock_instance
        mock_async_client = MagicMock()
        mock_async_anthropic_class.return_value = mock_async_client

        result = factory.get_chat_completion_for_model_name(
            "claude-3-5-sonnet-20240620", "claude_service"
        )

        # Verify AsyncAnthropic was called correctly
        mock_async_anthropic_class.assert_called_once_with(
            api_key="unused",
            base_url="https://test-endpoint.example.com/anthropic/claude-3-5-sonnet-20240620-v1",
            default_headers={"X-Custom-Header": "test_api_key_12345"},
        )

        # Verify AnthropicChatCompletion was called correctly
        mock_anthropic_class.assert_called_once_with(
            service_id="claude_service",
            api_key="unused",
            ai_model_id="claude-3-5-sonnet-20240620",
            async_client=mock_async_client,
        )
        assert result == mock_instance

    @patch("sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AsyncAnthropic")
    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AnthropicChatCompletion"
    )
    def test_claude_haiku_model_creates_anthropic_completion(
        self, mock_anthropic_class, mock_async_anthropic_class, factory
    ):
        """Test that Claude Haiku model creates an AnthropicChatCompletion instance."""
        mock_instance = MagicMock()
        mock_anthropic_class.return_value = mock_instance
        mock_async_client = MagicMock()
        mock_async_anthropic_class.return_value = mock_async_client

        result = factory.get_chat_completion_for_model_name(
            "claude-3-haiku-20240307", "haiku_service"
        )

        # Verify the correct base_url is constructed for Haiku
        call_kwargs = mock_async_anthropic_class.call_args.kwargs
        assert (
            call_kwargs["base_url"]
            == "https://test-endpoint.example.com/anthropic/claude-3-haiku-20240307-v1"
        )
        assert result == mock_instance

    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.GoogleAIChatCompletion"
    )
    def test_google_model_creates_google_completion(self, mock_google_class, factory):
        """Test that Google model creates a GoogleAIChatCompletion instance."""
        mock_instance = MagicMock()
        mock_google_class.return_value = mock_instance

        result = factory.get_chat_completion_for_model_name("gemini-2-0-flash", "gemini_service")

        # Verify GoogleAIChatCompletion was called with correct parameters
        mock_google_class.assert_called_once_with(
            service_id="gemini_service",
            deployment_name="gemini-2-0-flash",
            api_key="test_api_key_12345",
        )
        assert result == mock_instance

    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.GoogleAIChatCompletion"
    )
    def test_gemini_pro_model_creates_google_completion(self, mock_google_class, factory):
        """Test that Gemini Pro model creates a GoogleAIChatCompletion instance."""
        mock_instance = MagicMock()
        mock_google_class.return_value = mock_instance

        result = factory.get_chat_completion_for_model_name(
            "gemini-2-5-pro-preview-03-25", "pro_service"
        )

        call_kwargs = mock_google_class.call_args.kwargs
        assert call_kwargs["deployment_name"] == "gemini-2-5-pro-preview-03-25"
        assert result == mock_instance

    def test_unsupported_model_raises_value_error(self, factory):
        """Test that an unsupported model raises ValueError."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("unsupported-model", "test_service")

    def test_empty_model_name_raises_value_error(self, factory):
        """Test that an empty model name raises ValueError."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("", "test_service")


class TestGetModelTypeForName:
    """Test get_model_type_for_name method."""

    def test_openai_model_returns_openai_type(self, factory):
        """Test that OpenAI model returns ModelType.OPENAI."""
        result = factory.get_model_type_for_name("gpt-4o-2024-05-13")
        assert result == ModelType.OPENAI

    def test_gpt_35_turbo_returns_openai_type(self, factory):
        """Test that GPT-3.5 Turbo returns ModelType.OPENAI."""
        result = factory.get_model_type_for_name("gpt-35-turbo-0125")
        assert result == ModelType.OPENAI

    def test_gpt_4_turbo_returns_openai_type(self, factory):
        """Test that GPT-4 Turbo returns ModelType.OPENAI."""
        result = factory.get_model_type_for_name("gpt-4-turbo-2024-04-09")
        assert result == ModelType.OPENAI

    def test_anthropic_model_returns_anthropic_type(self, factory):
        """Test that Anthropic model returns ModelType.ANTHROPIC."""
        result = factory.get_model_type_for_name("claude-3-5-sonnet-20240620")
        assert result == ModelType.ANTHROPIC

    def test_claude_haiku_returns_anthropic_type(self, factory):
        """Test that Claude Haiku returns ModelType.ANTHROPIC."""
        result = factory.get_model_type_for_name("claude-3-haiku-20240307")
        assert result == ModelType.ANTHROPIC

    def test_google_model_returns_google_type(self, factory):
        """Test that Google model returns ModelType.GOOGLE."""
        result = factory.get_model_type_for_name("gemini-2-0-flash")
        assert result == ModelType.GOOGLE

    def test_gemini_pro_returns_google_type(self, factory):
        """Test that Gemini Pro returns ModelType.GOOGLE."""
        result = factory.get_model_type_for_name("gemini-2-5-pro-preview-03-25")
        assert result == ModelType.GOOGLE

    def test_gemini_flash_lite_returns_google_type(self, factory):
        """Test that Gemini Flash Lite returns ModelType.GOOGLE."""
        result = factory.get_model_type_for_name("gemini-2-0-flash-lite")
        assert result == ModelType.GOOGLE

    def test_unsupported_model_raises_value_error(self, factory):
        """Test that an unsupported model raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name unsupported-model"):
            factory.get_model_type_for_name("unsupported-model")

    def test_empty_model_name_raises_value_error(self, factory):
        """Test that an empty model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name"):
            factory.get_model_type_for_name("")


class TestModelSupportsStructuredOutput:
    """Test model_supports_structured_output method."""

    def test_openai_model_supports_structured_output(self, factory):
        """Test that OpenAI model supports structured output."""
        result = factory.model_supports_structured_output("gpt-4o-2024-05-13")
        assert result is True

    def test_gpt_35_turbo_supports_structured_output(self, factory):
        """Test that GPT-3.5 Turbo supports structured output."""
        result = factory.model_supports_structured_output("gpt-35-turbo-1106")
        assert result is True

    def test_gpt_4o_mini_supports_structured_output(self, factory):
        """Test that GPT-4o Mini supports structured output."""
        result = factory.model_supports_structured_output("gpt-4o-mini-2024-07-18")
        assert result is True

    def test_anthropic_model_does_not_support_structured_output(self, factory):
        """Test that Anthropic model does not support structured output."""
        result = factory.model_supports_structured_output("claude-3-5-sonnet-20240620")
        assert result is False

    def test_claude_haiku_does_not_support_structured_output(self, factory):
        """Test that Claude Haiku does not support structured output."""
        result = factory.model_supports_structured_output("claude-3-haiku-20240307")
        assert result is False

    def test_google_model_supports_structured_output(self, factory):
        """Test that Google model supports structured output."""
        result = factory.model_supports_structured_output("gemini-2-0-flash")
        assert result is True

    def test_gemini_pro_supports_structured_output(self, factory):
        """Test that Gemini Pro supports structured output."""
        result = factory.model_supports_structured_output("gemini-2-5-pro-preview-03-25")
        assert result is True

    def test_gemini_flash_lite_supports_structured_output(self, factory):
        """Test that Gemini Flash Lite supports structured output."""
        result = factory.model_supports_structured_output("gemini-2-0-flash-lite")
        assert result is True

    def test_unsupported_model_raises_value_error(self, factory):
        """Test that an unsupported model raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name unsupported-model"):
            factory.model_supports_structured_output("unsupported-model")

    def test_empty_model_name_raises_value_error(self, factory):
        """Test that an empty model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name"):
            factory.model_supports_structured_output("")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_case_sensitive_model_names(self, factory):
        """Test that model names are case-sensitive."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("GPT-4O-2024-05-13", "test_service")

        with pytest.raises(ValueError, match="Unknown model name GPT-4O-2024-05-13"):
            factory.get_model_type_for_name("GPT-4O-2024-05-13")

        with pytest.raises(ValueError, match="Unknown model name CLAUDE-3-5-SONNET-20240620"):
            factory.model_supports_structured_output("CLAUDE-3-5-SONNET-20240620")

    def test_whitespace_model_names_not_supported(self, factory):
        """Test that model names with whitespace are not supported."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name(" gpt-4o-2024-05-13 ", "test_service")

    def test_partial_model_name_not_supported(self, factory):
        """Test that partial model names are not supported."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("gpt-4o", "test_service")

        with pytest.raises(ValueError, match="Unknown model name claude"):
            factory.get_model_type_for_name("claude")

    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AzureChatCompletion"
    )
    def test_multiple_calls_with_same_model(self, mock_azure_class, factory):
        """Test that multiple calls with the same model work correctly."""
        mock_azure_class.return_value = MagicMock()

        factory.get_chat_completion_for_model_name("gpt-4o-2024-05-13", "service1")
        factory.get_chat_completion_for_model_name("gpt-4o-2024-05-13", "service2")

        assert mock_azure_class.call_count == 2

    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AzureChatCompletion"
    )
    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.GoogleAIChatCompletion"
    )
    def test_different_service_ids_for_different_models(
        self, mock_google_class, mock_azure_class, factory
    ):
        """Test that different service IDs are passed correctly for different models."""
        mock_azure_class.return_value = MagicMock()
        mock_google_class.return_value = MagicMock()

        factory.get_chat_completion_for_model_name("gpt-4o-2024-05-13", "service_alpha")
        factory.get_chat_completion_for_model_name("gemini-2-0-flash", "service_beta")

        azure_calls = mock_azure_class.call_args_list
        google_calls = mock_google_class.call_args_list
        assert azure_calls[0].kwargs["service_id"] == "service_alpha"
        assert google_calls[0].kwargs["service_id"] == "service_beta"

    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AzureChatCompletion"
    )
    def test_url_construction_for_openai(self, mock_azure_class, factory):
        """Test that the URL is correctly constructed for OpenAI models."""
        mock_azure_class.return_value = MagicMock()

        factory.get_chat_completion_for_model_name("gpt-4o-2024-05-13", "test_service")

        call_kwargs = mock_azure_class.call_args.kwargs
        assert call_kwargs["base_url"] == "https://test-endpoint.example.com/openai"

    @patch("sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AsyncAnthropic")
    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AnthropicChatCompletion"
    )
    def test_url_construction_for_anthropic(
        self, mock_anthropic_class, mock_async_anthropic_class, factory
    ):
        """Test that the URL is correctly constructed for Anthropic models."""
        mock_anthropic_class.return_value = MagicMock()
        mock_async_anthropic_class.return_value = MagicMock()

        factory.get_chat_completion_for_model_name("claude-3-5-sonnet-20240620", "test_service")

        call_kwargs = mock_async_anthropic_class.call_args.kwargs
        assert (
            call_kwargs["base_url"]
            == "https://test-endpoint.example.com/anthropic/claude-3-5-sonnet-20240620-v1"
        )

    @patch("sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AsyncAnthropic")
    @patch(
        "sk_agents.chat_completion.custom.example_custom_chat_completion_factory.AnthropicChatCompletion"
    )
    def test_custom_header_passed_to_anthropic(
        self, mock_anthropic_class, mock_async_anthropic_class, factory
    ):
        """Test that custom header with API key is passed to Anthropic async client."""
        mock_anthropic_class.return_value = MagicMock()
        mock_async_anthropic_class.return_value = MagicMock()

        factory.get_chat_completion_for_model_name("claude-3-5-sonnet-20240620", "test_service")

        call_kwargs = mock_async_anthropic_class.call_args.kwargs
        assert call_kwargs["default_headers"] == {"X-Custom-Header": "test_api_key_12345"}

    def test_all_openai_models_recognized(self, factory):
        """Test that all OpenAI models in the list are recognized."""
        openai_models = [
            "gpt-35-turbo-1106",
            "gpt-35-turbo-0125",
            "gpt-4o-2024-05-13",
            "gpt-4o-2024-08-06",
            "gpt-4o-mini-2024-07-18",
            "gpt-4-turbo-2024-04-09",
        ]
        for model in openai_models:
            model_type = factory.get_model_type_for_name(model)
            assert model_type == ModelType.OPENAI

    def test_all_anthropic_models_recognized(self, factory):
        """Test that all Anthropic models in the list are recognized."""
        anthropic_models = [
            "claude-3-5-sonnet-20240620",
            "claude-3-haiku-20240307",
        ]
        for model in anthropic_models:
            model_type = factory.get_model_type_for_name(model)
            assert model_type == ModelType.ANTHROPIC

    def test_all_google_models_recognized(self, factory):
        """Test that all Google models in the list are recognized."""
        google_models = [
            "gemini-2-5-pro-preview-03-25",
            "gemini-2-5-flash-preview-04-17",
            "gemini-2-0-flash",
            "gemini-2-0-flash-lite",
        ]
        for model in google_models:
            model_type = factory.get_model_type_for_name(model)
            assert model_type == ModelType.GOOGLE
