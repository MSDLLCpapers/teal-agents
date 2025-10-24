from unittest.mock import MagicMock, patch

import pytest

from sk_agents.chat_completion.default_chat_completion_factory import (
    DefaultChatCompletionFactory,
)
from sk_agents.configs import TA_API_KEY
from sk_agents.ska_types import ModelType


@pytest.fixture
def mock_app_config():
    """Create a mock app config for testing."""
    config = MagicMock()
    config.get.return_value = "test_api_key_12345"
    return config


@pytest.fixture
def factory(mock_app_config):
    """Create a DefaultChatCompletionFactory instance."""
    return DefaultChatCompletionFactory(mock_app_config)


class TestGetConfigs:
    """Test get_configs static method."""

    def test_get_configs_returns_none(self):
        """Test that get_configs returns None."""
        result = DefaultChatCompletionFactory.get_configs()
        assert result is None


class TestGetChatCompletionForModelName:
    """Test get_chat_completion_for_model_name method."""

    @patch("sk_agents.chat_completion.default_chat_completion_factory.OpenAIChatCompletion")
    def test_gpt_4o_model_creates_openai_completion(
        self, mock_openai_class, factory, mock_app_config
    ):
        """Test that gpt-4o creates an OpenAIChatCompletion instance."""
        mock_instance = MagicMock()
        mock_openai_class.return_value = mock_instance

        result = factory.get_chat_completion_for_model_name("gpt-4o", "test_service")

        # Verify OpenAIChatCompletion was called with correct parameters
        mock_openai_class.assert_called_once_with(
            service_id="test_service",
            ai_model_id="gpt-4o",
            api_key="test_api_key_12345",
        )
        assert result == mock_instance

    @patch("sk_agents.chat_completion.default_chat_completion_factory.OpenAIChatCompletion")
    def test_gpt_4o_mini_model_creates_openai_completion(
        self, mock_openai_class, factory, mock_app_config
    ):
        """Test that gpt-4o-mini creates an OpenAIChatCompletion instance."""
        mock_instance = MagicMock()
        mock_openai_class.return_value = mock_instance

        result = factory.get_chat_completion_for_model_name("gpt-4o-mini", "mini_service")

        # Verify OpenAIChatCompletion was called with correct parameters
        mock_openai_class.assert_called_once_with(
            service_id="mini_service",
            ai_model_id="gpt-4o-mini",
            api_key="test_api_key_12345",
        )
        assert result == mock_instance

    def test_unsupported_model_raises_value_error(self, factory):
        """Test that an unsupported model raises ValueError."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("unsupported-model", "test_service")

    def test_empty_model_name_raises_value_error(self, factory):
        """Test that an empty model name raises ValueError."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("", "test_service")

    def test_anthropic_model_raises_value_error(self, factory):
        """Test that an Anthropic model raises ValueError."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("claude-3-opus", "test_service")

    @patch("sk_agents.chat_completion.default_chat_completion_factory.OpenAIChatCompletion")
    def test_api_key_retrieved_from_config(self, mock_openai_class, mock_app_config):
        """Test that API key is correctly retrieved from app_config."""
        mock_app_config.get.return_value = "custom_api_key_xyz"
        factory = DefaultChatCompletionFactory(mock_app_config)

        factory.get_chat_completion_for_model_name("gpt-4o", "test_service")

        # Verify the API key was requested from config
        mock_app_config.get.assert_called_with(TA_API_KEY.env_name)
        # Verify it was passed to OpenAIChatCompletion
        call_kwargs = mock_openai_class.call_args.kwargs
        assert call_kwargs["api_key"] == "custom_api_key_xyz"


class TestGetModelTypeForName:
    """Test get_model_type_for_name method."""

    def test_gpt_4o_returns_openai_type(self, factory):
        """Test that gpt-4o returns ModelType.OPENAI."""
        result = factory.get_model_type_for_name("gpt-4o")
        assert result == ModelType.OPENAI

    def test_gpt_4o_mini_returns_openai_type(self, factory):
        """Test that gpt-4o-mini returns ModelType.OPENAI."""
        result = factory.get_model_type_for_name("gpt-4o-mini")
        assert result == ModelType.OPENAI

    def test_unsupported_model_raises_value_error(self, factory):
        """Test that an unsupported model raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name unsupported-model"):
            factory.get_model_type_for_name("unsupported-model")

    def test_empty_model_name_raises_value_error(self, factory):
        """Test that an empty model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name"):
            factory.get_model_type_for_name("")

    def test_anthropic_model_raises_value_error(self, factory):
        """Test that an Anthropic model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name claude-3-opus"):
            factory.get_model_type_for_name("claude-3-opus")

    def test_google_model_raises_value_error(self, factory):
        """Test that a Google model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name gemini-pro"):
            factory.get_model_type_for_name("gemini-pro")


class TestModelSupportsStructuredOutput:
    """Test model_supports_structured_output method."""

    def test_gpt_4o_supports_structured_output(self, factory):
        """Test that gpt-4o supports structured output."""
        result = factory.model_supports_structured_output("gpt-4o")
        assert result is True

    def test_gpt_4o_mini_supports_structured_output(self, factory):
        """Test that gpt-4o-mini supports structured output."""
        result = factory.model_supports_structured_output("gpt-4o-mini")
        assert result is True

    def test_unsupported_model_raises_value_error(self, factory):
        """Test that an unsupported model raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name unsupported-model"):
            factory.model_supports_structured_output("unsupported-model")

    def test_empty_model_name_raises_value_error(self, factory):
        """Test that an empty model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name"):
            factory.model_supports_structured_output("")

    def test_anthropic_model_raises_value_error(self, factory):
        """Test that an Anthropic model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown model name claude-3-opus"):
            factory.model_supports_structured_output("claude-3-opus")


class TestFactoryInitialization:
    """Test factory initialization and configuration."""

    def test_factory_inherits_from_chat_completion_factory(self, factory):
        """Test that DefaultChatCompletionFactory inherits from ChatCompletionFactory."""
        from sk_agents.ska_types import ChatCompletionFactory

        assert isinstance(factory, ChatCompletionFactory)

    def test_factory_stores_app_config(self, mock_app_config):
        """Test that factory stores the app_config."""
        factory = DefaultChatCompletionFactory(mock_app_config)
        assert factory.app_config is mock_app_config

    def test_openai_models_list_contains_expected_models(self):
        """Test that the OPENAI_MODELS list contains expected models."""
        assert "gpt-4o" in DefaultChatCompletionFactory._OPENAI_MODELS
        assert "gpt-4o-mini" in DefaultChatCompletionFactory._OPENAI_MODELS
        assert len(DefaultChatCompletionFactory._OPENAI_MODELS) == 2


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_case_sensitive_model_names(self, factory):
        """Test that model names are case-sensitive."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("GPT-4O", "test_service")

        with pytest.raises(ValueError, match="Unknown model name GPT-4O"):
            factory.get_model_type_for_name("GPT-4O")

        with pytest.raises(ValueError, match="Unknown model name GPT-4O"):
            factory.model_supports_structured_output("GPT-4O")

    def test_whitespace_model_names_not_supported(self, factory):
        """Test that model names with whitespace are not supported."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name(" gpt-4o ", "test_service")

    def test_partial_model_name_not_supported(self, factory):
        """Test that partial model names are not supported."""
        with pytest.raises(ValueError, match="Model type not supported"):
            factory.get_chat_completion_for_model_name("gpt-4", "test_service")

        with pytest.raises(ValueError, match="Unknown model name gpt"):
            factory.get_model_type_for_name("gpt")

    @patch("sk_agents.chat_completion.default_chat_completion_factory.OpenAIChatCompletion")
    def test_multiple_calls_with_same_model(self, mock_openai_class, factory):
        """Test that multiple calls with the same model work correctly."""
        mock_openai_class.return_value = MagicMock()

        factory.get_chat_completion_for_model_name("gpt-4o", "service1")
        factory.get_chat_completion_for_model_name("gpt-4o", "service2")

        assert mock_openai_class.call_count == 2

    @patch("sk_agents.chat_completion.default_chat_completion_factory.OpenAIChatCompletion")
    def test_different_service_ids(self, mock_openai_class, factory):
        """Test that different service IDs are passed correctly."""
        mock_openai_class.return_value = MagicMock()

        factory.get_chat_completion_for_model_name("gpt-4o", "service_alpha")
        factory.get_chat_completion_for_model_name("gpt-4o-mini", "service_beta")

        calls = mock_openai_class.call_args_list
        assert calls[0].kwargs["service_id"] == "service_alpha"
        assert calls[1].kwargs["service_id"] == "service_beta"
