from unittest.mock import MagicMock, patch

import pytest

from sk_agents.configs import (
    TA_API_KEY,
    TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME,
    TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE,
)
from sk_agents.ska_types import ModelType
from sk_agents.tealagents.chat_completion_builder import ChatCompletionBuilder


@pytest.fixture
def mock_app_config_no_custom():
    """Create a mock app config without custom factory."""
    config = MagicMock()
    config.get.side_effect = lambda key: {
        TA_API_KEY.env_name: "test_api_key_12345",
        TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: None,
    }.get(key, None)
    return config


@pytest.fixture
def mock_app_config_with_custom():
    """Create a mock app config with custom factory configured."""
    config = MagicMock()
    config.get.side_effect = lambda key: {
        TA_API_KEY.env_name: "test_api_key_12345",
        TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
        TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
    }.get(key, None)
    return config


@pytest.fixture
def mock_custom_factory():
    """Create a mock custom chat completion factory."""
    factory = MagicMock()
    factory.get_chat_completion_for_model_name.return_value = MagicMock()
    factory.get_model_type_for_name.return_value = ModelType.OPENAI
    factory.model_supports_structured_output.return_value = True
    return factory


class TestInitialization:
    """Test ChatCompletionBuilder initialization."""

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    def test_init_without_custom_factory(
        self, mock_default_factory_class, mock_app_config_no_custom
    ):
        """Test initialization without custom factory configured."""
        mock_default_factory_instance = MagicMock()
        mock_default_factory_class.return_value = mock_default_factory_instance

        builder = ChatCompletionBuilder(mock_app_config_no_custom)

        assert builder.app_config is mock_app_config_no_custom
        assert builder.ccc_factory is None
        assert builder.self_default_cc_factory is mock_default_factory_instance
        mock_default_factory_class.assert_called_once_with(mock_app_config_no_custom)

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    @patch("sk_agents.tealagents.chat_completion_builder.AppConfig")
    def test_init_with_custom_factory(
        self,
        mock_app_config_class,
        mock_module_loader,
        mock_default_factory_class,
        mock_app_config_with_custom,
        mock_custom_factory,
    ):
        """Test initialization with custom factory configured."""
        # Setup mock module with factory class
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        builder = ChatCompletionBuilder(mock_app_config_with_custom)

        assert builder.ccc_factory is mock_custom_factory
        mock_module_loader.load_module.assert_called_once_with("test_module")
        mock_factory_class.assert_called_once_with(mock_app_config_with_custom)

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_init_custom_factory_missing_class_name(
        self, mock_module_loader, mock_default_factory_class
    ):
        """Test initialization fails when custom module is set but class name is missing."""
        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: None,
        }.get(key, None)

        with pytest.raises(
            ValueError, match="Custom Chat Completion Factory class name not provided"
        ):
            ChatCompletionBuilder(config)

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_init_custom_factory_class_not_found(
        self, mock_module_loader, mock_default_factory_class
    ):
        """Test initialization fails when custom class is not found in module."""
        mock_module = MagicMock(spec=[])  # Empty spec means no attributes
        mock_module_loader.load_module.return_value = mock_module

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "MissingFactory",
        }.get(key, None)

        with pytest.raises(
            ValueError,
            match=(
                "Custom Chat Completion Factory class: MissingFactory"
                "Not found in module: test_module"
            ),
        ):
            ChatCompletionBuilder(config)

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    @patch("sk_agents.tealagents.chat_completion_builder.AppConfig")
    def test_init_with_custom_factory_configs(
        self,
        mock_app_config_class,
        mock_module_loader,
        mock_default_factory_class,
    ):
        """Test initialization adds custom factory configs when provided."""
        mock_config1 = MagicMock()
        mock_config2 = MagicMock()
        mock_configs = [mock_config1, mock_config2]

        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = mock_configs
        mock_factory_instance = MagicMock()
        mock_factory_class.return_value = mock_factory_instance
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)

        mock_app_config_class.add_configs.assert_called_once_with(mock_configs)
        assert builder.ccc_factory is mock_factory_instance


class TestGetChatCompletionForModel:
    """Test get_chat_completion_for_model method."""

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    def test_get_chat_completion_without_custom_factory(
        self, mock_default_factory_class, mock_app_config_no_custom
    ):
        """Test get_chat_completion_for_model uses default factory when no custom factory."""
        mock_default_instance = MagicMock()
        mock_completion = MagicMock()
        mock_default_instance.get_chat_completion_for_model_name.return_value = mock_completion
        mock_default_factory_class.return_value = mock_default_instance

        builder = ChatCompletionBuilder(mock_app_config_no_custom)
        result = builder.get_chat_completion_for_model("service-1", "gpt-4o")

        assert result is mock_completion
        mock_default_instance.get_chat_completion_for_model_name.assert_called_once_with(
            "gpt-4o", "service-1"
        )

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_get_chat_completion_with_custom_factory_success(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test get_chat_completion_for_model uses custom factory when available."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_completion = MagicMock()
        mock_custom_factory.get_chat_completion_for_model_name.return_value = mock_completion
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)
        result = builder.get_chat_completion_for_model("service-1", "custom-model")

        assert result is mock_completion
        mock_custom_factory.get_chat_completion_for_model_name.assert_called_once_with(
            "custom-model", "service-1"
        )

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_get_chat_completion_custom_factory_fallback_to_default(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test fallback to default factory when custom factory raises ValueError."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_custom_factory.get_chat_completion_for_model_name.side_effect = ValueError(
            "Model not supported"
        )
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        mock_default_instance = MagicMock()
        mock_default_completion = MagicMock()
        mock_default_instance.get_chat_completion_for_model_name.return_value = (
            mock_default_completion
        )
        mock_default_factory_class.return_value = mock_default_instance

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)
        result = builder.get_chat_completion_for_model("service-1", "gpt-4o")

        assert result is mock_default_completion
        mock_custom_factory.get_chat_completion_for_model_name.assert_called_once_with(
            "gpt-4o", "service-1"
        )
        mock_default_instance.get_chat_completion_for_model_name.assert_called_once_with(
            "gpt-4o", "service-1"
        )


class TestGetModelTypeForName:
    """Test get_model_type_for_name method."""

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    def test_get_model_type_without_custom_factory(
        self, mock_default_factory_class, mock_app_config_no_custom
    ):
        """Test get_model_type_for_name uses default factory when no custom factory."""
        mock_default_instance = MagicMock()
        mock_default_instance.get_model_type_for_name.return_value = ModelType.OPENAI
        mock_default_factory_class.return_value = mock_default_instance

        builder = ChatCompletionBuilder(mock_app_config_no_custom)
        result = builder.get_model_type_for_name("gpt-4o")

        assert result == ModelType.OPENAI
        mock_default_instance.get_model_type_for_name.assert_called_once_with("gpt-4o")

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_get_model_type_with_custom_factory_success(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test get_model_type_for_name uses custom factory when available."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_custom_factory.get_model_type_for_name.return_value = ModelType.ANTHROPIC
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)
        result = builder.get_model_type_for_name("claude-3")

        assert result == ModelType.ANTHROPIC
        mock_custom_factory.get_model_type_for_name.assert_called_once_with("claude-3")

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_get_model_type_custom_factory_fallback_to_default(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test fallback to default factory when custom factory raises ValueError."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_custom_factory.get_model_type_for_name.side_effect = ValueError("Unknown model")
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        mock_default_instance = MagicMock()
        mock_default_instance.get_model_type_for_name.return_value = ModelType.GOOGLE
        mock_default_factory_class.return_value = mock_default_instance

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)
        result = builder.get_model_type_for_name("gemini-pro")

        assert result == ModelType.GOOGLE
        mock_custom_factory.get_model_type_for_name.assert_called_once_with("gemini-pro")
        mock_default_instance.get_model_type_for_name.assert_called_once_with("gemini-pro")


class TestModelSupportsStructuredOutput:
    """Test model_supports_structured_output method."""

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    def test_supports_structured_output_without_custom_factory(
        self, mock_default_factory_class, mock_app_config_no_custom
    ):
        """Test model_supports_structured_output uses default factory when no custom factory."""
        mock_default_instance = MagicMock()
        mock_default_instance.model_supports_structured_output.return_value = True
        mock_default_factory_class.return_value = mock_default_instance

        builder = ChatCompletionBuilder(mock_app_config_no_custom)
        result = builder.model_supports_structured_output("gpt-4o")

        assert result is True
        mock_default_instance.model_supports_structured_output.assert_called_once_with("gpt-4o")

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_supports_structured_output_with_custom_factory_success(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test model_supports_structured_output uses custom factory when available."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_custom_factory.model_supports_structured_output.return_value = False
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)
        result = builder.model_supports_structured_output("claude-3")

        assert result is False
        mock_custom_factory.model_supports_structured_output.assert_called_once_with("claude-3")

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_supports_structured_output_custom_factory_fallback_to_default(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test fallback to default factory when custom factory raises ValueError."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_custom_factory.model_supports_structured_output.side_effect = ValueError(
            "Unknown model"
        )
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        mock_default_instance = MagicMock()
        mock_default_instance.model_supports_structured_output.return_value = True
        mock_default_factory_class.return_value = mock_default_instance

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)
        result = builder.model_supports_structured_output("gemini-pro")

        assert result is True
        mock_custom_factory.model_supports_structured_output.assert_called_once_with("gemini-pro")
        mock_default_instance.model_supports_structured_output.assert_called_once_with("gemini-pro")


class TestLogging:
    """Test logging behavior."""

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_logs_warning_on_custom_factory_chat_completion_error(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test that a warning is logged when custom factory fails for get_chat_completion."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_custom_factory.get_chat_completion_for_model_name.side_effect = ValueError()
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        mock_default_instance = MagicMock()
        mock_default_factory_class.return_value = mock_default_instance

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)

        with patch.object(builder.logger, "warning") as mock_warning:
            builder.get_chat_completion_for_model("service-1", "test-model")
            mock_warning.assert_called_once_with(
                "Could not find model test-model using custom factory"
            )

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_logs_warning_on_custom_factory_model_type_error(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test that a warning is logged when custom factory fails for get_model_type."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_custom_factory.get_model_type_for_name.side_effect = ValueError()
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        mock_default_instance = MagicMock()
        mock_default_factory_class.return_value = mock_default_instance

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)

        with patch.object(builder.logger, "warning") as mock_warning:
            builder.get_model_type_for_name("test-model")
            mock_warning.assert_called_once_with(
                "Could not find model test-model using custom factory"
            )

    @patch("sk_agents.tealagents.chat_completion_builder.DefaultChatCompletionFactory")
    @patch("sk_agents.tealagents.chat_completion_builder.ModuleLoader")
    def test_logs_warning_on_custom_factory_structured_output_error(
        self, mock_module_loader, mock_default_factory_class, mock_custom_factory
    ):
        """Test that a warning is logged when custom factory fails for structured output check."""
        mock_module = MagicMock()
        mock_factory_class = MagicMock()
        mock_factory_class.get_configs.return_value = None
        mock_custom_factory.model_supports_structured_output.side_effect = ValueError()
        mock_factory_class.return_value = mock_custom_factory
        mock_module.TestFactory = mock_factory_class
        mock_module_loader.load_module.return_value = mock_module

        mock_default_instance = MagicMock()
        mock_default_factory_class.return_value = mock_default_instance

        config = MagicMock()
        config.get.side_effect = lambda key: {
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name: "test_module",
            TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name: "TestFactory",
        }.get(key, None)

        builder = ChatCompletionBuilder(config)

        with patch.object(builder.logger, "warning") as mock_warning:
            builder.model_supports_structured_output("test-model")
            mock_warning.assert_called_once_with(
                "Could not find model test-model using custom factory"
            )
