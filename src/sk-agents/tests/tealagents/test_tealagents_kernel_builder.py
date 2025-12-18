from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from semantic_kernel.kernel import Kernel
from ska_utils import AppConfig

from sk_agents.ska_types import ModelType
from sk_agents.tealagents.kernel_builder import KernelBuilder


@pytest.fixture
def mock_app_config():
    """Create a mock app config."""
    config = MagicMock(spec=AppConfig)
    return config


@pytest.fixture
def mock_chat_completion_builder():
    """Create a mock ChatCompletionBuilder."""
    builder = MagicMock()
    builder.get_chat_completion_for_model.return_value = MagicMock()
    builder.get_model_type_for_name.return_value = ModelType.OPENAI
    builder.model_supports_structured_output.return_value = True
    return builder


@pytest.fixture
def mock_remote_plugin_loader():
    """Create a mock RemotePluginLoader."""
    loader = MagicMock()
    loader.load_remote_plugins.return_value = None
    return loader


@pytest.fixture
def mock_auth_storage_manager():
    """Create a mock SecureAuthStorageManager."""
    manager = MagicMock()
    manager.retrieve.return_value = None
    return manager


@pytest.fixture
def mock_authorizer():
    """Create a mock RequestAuthorizer."""
    authorizer = MagicMock()
    authorizer.authorize_request = AsyncMock(return_value="user123")
    return authorizer


@pytest.fixture
def kernel_builder(
    mock_chat_completion_builder,
    mock_remote_plugin_loader,
    mock_app_config,
    mock_auth_storage_manager,
    mock_authorizer,
):
    """Create a KernelBuilder instance with mocked dependencies."""
    with (
        patch("sk_agents.tealagents.kernel_builder.AuthStorageFactory") as mock_auth_factory,
        patch("sk_agents.tealagents.kernel_builder.AuthorizerFactory") as mock_authorizer_factory,
    ):
        mock_auth_factory.return_value.get_auth_storage_manager.return_value = (
            mock_auth_storage_manager
        )
        mock_authorizer_factory.return_value.get_authorizer.return_value = mock_authorizer

        builder = KernelBuilder(
            chat_completion_builder=mock_chat_completion_builder,
            remote_plugin_loader=mock_remote_plugin_loader,
            app_config=mock_app_config,
            authorization="Bearer test_token",
        )

        builder.auth_storage_manager = mock_auth_storage_manager
        builder.authorizer = mock_authorizer

        return builder


class TestKernelBuilderInitialization:
    """Test KernelBuilder initialization."""

    @patch("sk_agents.tealagents.kernel_builder.AuthStorageFactory")
    @patch("sk_agents.tealagents.kernel_builder.AuthorizerFactory")
    def test_init_with_authorization(
        self,
        mock_authorizer_factory,
        mock_auth_factory,
        mock_chat_completion_builder,
        mock_remote_plugin_loader,
        mock_app_config,
    ):
        """Test initialization with authorization token."""
        mock_auth_storage = MagicMock()
        mock_auth_factory.return_value.get_auth_storage_manager.return_value = mock_auth_storage
        mock_auth = MagicMock()
        mock_authorizer_factory.return_value.get_authorizer.return_value = mock_auth

        builder = KernelBuilder(
            chat_completion_builder=mock_chat_completion_builder,
            remote_plugin_loader=mock_remote_plugin_loader,
            app_config=mock_app_config,
            authorization="Bearer token123",
        )

        assert builder.chat_completion_builder is mock_chat_completion_builder
        assert builder.remote_plugin_loader is mock_remote_plugin_loader
        assert builder.app_config is mock_app_config
        assert builder.authorization == "Bearer token123"
        assert builder.auth_storage_manager is mock_auth_storage
        assert builder.authorizer is mock_auth

    @patch("sk_agents.tealagents.kernel_builder.AuthStorageFactory")
    @patch("sk_agents.tealagents.kernel_builder.AuthorizerFactory")
    def test_init_without_authorization(
        self,
        mock_authorizer_factory,
        mock_auth_factory,
        mock_chat_completion_builder,
        mock_remote_plugin_loader,
        mock_app_config,
    ):
        """Test initialization without authorization token."""
        mock_auth_factory.return_value.get_auth_storage_manager.return_value = MagicMock()
        mock_authorizer_factory.return_value.get_authorizer.return_value = MagicMock()

        builder = KernelBuilder(
            chat_completion_builder=mock_chat_completion_builder,
            remote_plugin_loader=mock_remote_plugin_loader,
            app_config=mock_app_config,
        )

        assert builder.authorization is None


class TestBuildKernel:
    """Test build_kernel method."""

    @pytest.mark.asyncio
    async def test_build_kernel_with_no_plugins(self, kernel_builder):
        """Test building kernel with no plugins or remote plugins."""
        result = await kernel_builder.build_kernel(
            model_name="gpt-4o",
            service_id="test-service",
            plugins=[],
            remote_plugins=[],
        )

        assert isinstance(result, Kernel)
        kernel_builder.chat_completion_builder.get_chat_completion_for_model.assert_called_once_with(
            service_id="test-service", model_name="gpt-4o"
        )

    @pytest.mark.asyncio
    async def test_build_kernel_with_plugins(self, kernel_builder):
        """Test building kernel with plugins."""
        mock_plugin_loader = MagicMock()
        mock_plugin_class = MagicMock()
        mock_plugin_instance = MagicMock()
        mock_plugin_instance.description = "Test plugin description"
        mock_plugin_class.return_value = mock_plugin_instance
        mock_plugin_loader.get_plugins.return_value = {"test_plugin": mock_plugin_class}

        with patch(
            "sk_agents.tealagents.kernel_builder.get_plugin_loader",
            return_value=mock_plugin_loader,
        ):
            result = await kernel_builder.build_kernel(
                model_name="gpt-4o",
                service_id="test-service",
                plugins=["test_plugin"],
                remote_plugins=[],
                authorization="Bearer test_token",
            )

        assert isinstance(result, Kernel)
        mock_plugin_loader.get_plugins.assert_called_once_with(["test_plugin"])

    @pytest.mark.asyncio
    async def test_build_kernel_with_remote_plugins(self, kernel_builder):
        """Test building kernel with remote plugins."""
        result = await kernel_builder.build_kernel(
            model_name="gpt-4o",
            service_id="test-service",
            plugins=[],
            remote_plugins=["remote_plugin1"],
        )

        assert isinstance(result, Kernel)
        kernel_builder.remote_plugin_loader.load_remote_plugins.assert_called_once()

    @pytest.mark.asyncio
    async def test_build_kernel_with_extra_data_collector(self, kernel_builder):
        """Test building kernel with extra data collector."""
        mock_extra_data_collector = MagicMock()
        mock_plugin_loader = MagicMock()
        mock_plugin_class = MagicMock()
        mock_plugin_instance = MagicMock()
        mock_plugin_instance.description = "Test plugin"
        mock_plugin_class.return_value = mock_plugin_instance
        mock_plugin_loader.get_plugins.return_value = {"test_plugin": mock_plugin_class}

        with patch(
            "sk_agents.tealagents.kernel_builder.get_plugin_loader",
            return_value=mock_plugin_loader,
        ):
            result = await kernel_builder.build_kernel(
                model_name="gpt-4o",
                service_id="test-service",
                plugins=["test_plugin"],
                remote_plugins=[],
                extra_data_collector=mock_extra_data_collector,
            )

        assert isinstance(result, Kernel)
        mock_plugin_class.assert_called_once()
        call_args = mock_plugin_class.call_args
        assert call_args[0][1] is mock_extra_data_collector

    @pytest.mark.asyncio
    async def test_build_kernel_exception_handling(self, kernel_builder):
        """Test build_kernel exception handling and logging."""
        kernel_builder.chat_completion_builder.get_chat_completion_for_model.side_effect = (
            Exception("Test error")
        )

        with pytest.raises(Exception, match="Test error"):
            await kernel_builder.build_kernel(
                model_name="gpt-4o",
                service_id="test-service",
                plugins=[],
                remote_plugins=[],
            )


class TestGetModelTypeForName:
    """Test get_model_type_for_name method."""

    def test_get_model_type_success(self, kernel_builder):
        """Test getting model type successfully."""
        result = kernel_builder.get_model_type_for_name("gpt-4o")

        assert result == ModelType.OPENAI
        kernel_builder.chat_completion_builder.get_model_type_for_name.assert_called_once_with(
            "gpt-4o"
        )

    def test_get_model_type_exception_handling(self, kernel_builder):
        """Test get_model_type_for_name exception handling."""
        kernel_builder.chat_completion_builder.get_model_type_for_name.side_effect = Exception(
            "Model not found"
        )

        with pytest.raises(Exception, match="Model not found"):
            kernel_builder.get_model_type_for_name("unknown-model")


class TestModelSupportsStructuredOutput:
    """Test model_supports_structured_output method."""

    def test_model_supports_structured_output_true(self, kernel_builder):
        """Test checking if model supports structured output (true)."""
        result = kernel_builder.model_supports_structured_output("gpt-4o")

        assert result is True
        kernel_builder.chat_completion_builder.model_supports_structured_output.assert_called_once_with(
            "gpt-4o"
        )

    def test_model_supports_structured_output_false(self, kernel_builder):
        """Test checking if model supports structured output (false)."""
        kernel_builder.chat_completion_builder.model_supports_structured_output.return_value = False

        result = kernel_builder.model_supports_structured_output("claude-3")

        assert result is False


class TestCreateBaseKernel:
    """Test _create_base_kernel method."""

    def test_create_base_kernel_success(self, kernel_builder):
        """Test creating base kernel successfully."""
        mock_chat_completion = MagicMock()
        kernel_builder.chat_completion_builder.get_chat_completion_for_model.return_value = (
            mock_chat_completion
        )

        result = kernel_builder._create_base_kernel("gpt-4o", "test-service")

        assert isinstance(result, Kernel)
        kernel_builder.chat_completion_builder.get_chat_completion_for_model.assert_called_once_with(
            service_id="test-service", model_name="gpt-4o"
        )

    def test_create_base_kernel_exception_handling(self, kernel_builder):
        """Test _create_base_kernel exception handling."""
        kernel_builder.chat_completion_builder.get_chat_completion_for_model.side_effect = (
            Exception("Chat completion error")
        )

        with pytest.raises(Exception, match="Chat completion error"):
            kernel_builder._create_base_kernel("gpt-4o", "test-service")


class TestLoadRemotePlugins:
    """Test _load_remote_plugins method."""

    def test_load_remote_plugins_success(self, kernel_builder):
        """Test loading remote plugins successfully."""
        kernel = Kernel()
        remote_plugins = ["plugin1", "plugin2"]

        result = kernel_builder._load_remote_plugins(remote_plugins, kernel)

        assert result is kernel
        kernel_builder.remote_plugin_loader.load_remote_plugins.assert_called_once_with(
            kernel, remote_plugins
        )

    def test_load_remote_plugins_none(self, kernel_builder):
        """Test loading remote plugins when list is None."""
        kernel = Kernel()

        result = kernel_builder._load_remote_plugins(None, kernel)

        assert result is kernel
        kernel_builder.remote_plugin_loader.load_remote_plugins.assert_not_called()

    def test_load_remote_plugins_empty_list(self, kernel_builder):
        """Test loading remote plugins when list is empty."""
        kernel = Kernel()

        result = kernel_builder._load_remote_plugins([], kernel)

        assert result is kernel
        kernel_builder.remote_plugin_loader.load_remote_plugins.assert_not_called()

    def test_load_remote_plugins_exception_handling(self, kernel_builder):
        """Test _load_remote_plugins exception handling."""
        kernel = Kernel()
        kernel_builder.remote_plugin_loader.load_remote_plugins.side_effect = Exception(
            "Remote plugin error"
        )

        with pytest.raises(Exception, match="Remote plugin error"):
            kernel_builder._load_remote_plugins(["plugin1"], kernel)


class TestParsePlugins:
    """Test _parse_plugins method."""

    def test_parse_plugins_none(self, kernel_builder):
        """Test parsing plugins when list is None."""
        kernel = Kernel()

        result = kernel_builder._parse_plugins(None, kernel)

        assert result is kernel

    def test_parse_plugins_empty_list(self, kernel_builder):
        """Test parsing plugins when list is empty."""
        kernel = Kernel()

        result = kernel_builder._parse_plugins([], kernel)

        assert result is kernel

    def test_parse_plugins_with_plugins(self, kernel_builder):
        """Test parsing plugins successfully."""
        kernel = Kernel()
        mock_plugin_loader = MagicMock()
        mock_plugin_class = MagicMock()
        mock_plugin_instance = MagicMock()
        mock_plugin_instance.description = "Test plugin"
        mock_plugin_class.return_value = mock_plugin_instance
        mock_plugin_loader.get_plugins.return_value = {"test_plugin": mock_plugin_class}

        with patch(
            "sk_agents.tealagents.kernel_builder.get_plugin_loader",
            return_value=mock_plugin_loader,
        ):
            result = kernel_builder._parse_plugins(
                ["test_plugin"], kernel, authorization="Bearer token"
            )

        assert result is kernel
        mock_plugin_loader.get_plugins.assert_called_once_with(["test_plugin"])
        mock_plugin_class.assert_called_once()

    def test_parse_plugins_with_extra_data_collector(self, kernel_builder):
        """Test parsing plugins with extra data collector."""
        kernel = Kernel()
        mock_extra_data_collector = MagicMock()
        mock_plugin_loader = MagicMock()
        mock_plugin_class = MagicMock()
        mock_plugin_instance = MagicMock()
        mock_plugin_instance.description = "Test plugin"
        mock_plugin_class.return_value = mock_plugin_instance
        mock_plugin_loader.get_plugins.return_value = {"test_plugin": mock_plugin_class}

        with patch(
            "sk_agents.tealagents.kernel_builder.get_plugin_loader",
            return_value=mock_plugin_loader,
        ):
            result = kernel_builder._parse_plugins(
                ["test_plugin"], kernel, extra_data_collector=mock_extra_data_collector
            )

        assert result is kernel
        call_args = mock_plugin_class.call_args
        assert call_args[0][1] is mock_extra_data_collector

    def test_parse_plugins_multiple_plugins(self, kernel_builder):
        """Test parsing multiple plugins."""
        kernel = Kernel()
        mock_plugin_loader = MagicMock()
        mock_plugin_class1 = MagicMock()
        mock_plugin_class2 = MagicMock()
        mock_plugin_instance1 = MagicMock()
        mock_plugin_instance1.description = "Plugin 1"
        mock_plugin_instance2 = MagicMock()
        mock_plugin_instance2.description = "Plugin 2"
        mock_plugin_class1.return_value = mock_plugin_instance1
        mock_plugin_class2.return_value = mock_plugin_instance2
        mock_plugin_loader.get_plugins.return_value = {
            "plugin1": mock_plugin_class1,
            "plugin2": mock_plugin_class2,
        }

        with patch(
            "sk_agents.tealagents.kernel_builder.get_plugin_loader",
            return_value=mock_plugin_loader,
        ):
            result = kernel_builder._parse_plugins(["plugin1", "plugin2"], kernel)

        assert result is kernel
        mock_plugin_class1.assert_called_once()
        mock_plugin_class2.assert_called_once()


class TestGetPluginAuthorization:
    """Test _get_plugin_authorization method."""

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_no_auth(self, kernel_builder):
        """Test getting plugin authorization when no original authorization provided."""
        result = await kernel_builder._get_plugin_authorization("test_plugin", None)

        assert result is None

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_with_cached_token(self, kernel_builder):
        """Test getting plugin authorization with cached token."""
        mock_cached_auth_data = MagicMock()
        mock_cached_auth_data.access_token = "cached_token_123"
        kernel_builder.auth_storage_manager.retrieve.return_value = mock_cached_auth_data
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value="user123")

        result = await kernel_builder._get_plugin_authorization(
            "test_plugin", "Bearer original_token"
        )

        assert result == "Bearer cached_token_123"
        kernel_builder.authorizer.authorize_request.assert_called_once_with("Bearer original_token")
        kernel_builder.auth_storage_manager.retrieve.assert_called_once_with(
            "user123", "test_plugin"
        )

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_no_cached_token(self, kernel_builder):
        """Test getting plugin authorization when no cached token exists."""
        kernel_builder.auth_storage_manager.retrieve.return_value = None
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value="user123")

        result = await kernel_builder._get_plugin_authorization(
            "test_plugin", "Bearer original_token"
        )

        assert result is None
        kernel_builder.auth_storage_manager.retrieve.assert_called_once_with(
            "user123", "test_plugin"
        )

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_cached_data_no_token(self, kernel_builder):
        """Test getting plugin authorization when cached data exists but has no access_token."""
        mock_cached_auth_data = MagicMock(spec=[])  # No access_token attribute
        kernel_builder.auth_storage_manager.retrieve.return_value = mock_cached_auth_data
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value="user123")

        result = await kernel_builder._get_plugin_authorization(
            "test_plugin", "Bearer original_token"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_no_user_id(self, kernel_builder):
        """Test getting plugin authorization when user ID cannot be extracted."""
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value=None)

        result = await kernel_builder._get_plugin_authorization(
            "test_plugin", "Bearer original_token"
        )

        assert result == "Bearer original_token"
        kernel_builder.auth_storage_manager.retrieve.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_authorizer_exception(self, kernel_builder):
        """Test getting plugin authorization when authorizer raises exception."""
        kernel_builder.authorizer.authorize_request = AsyncMock(
            side_effect=Exception("Authorization failed")
        )

        result = await kernel_builder._get_plugin_authorization(
            "test_plugin", "Bearer original_token"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_retrieve_exception(self, kernel_builder):
        """Test getting plugin authorization when retrieve raises exception."""
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value="user123")
        kernel_builder.auth_storage_manager.retrieve.side_effect = Exception("Retrieve failed")

        result = await kernel_builder._get_plugin_authorization(
            "test_plugin", "Bearer original_token"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_empty_user_id(self, kernel_builder):
        """Test getting plugin authorization when user ID is empty string."""
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value="")

        result = await kernel_builder._get_plugin_authorization(
            "test_plugin", "Bearer original_token"
        )

        assert result == "Bearer original_token"


class TestLogging:
    """Test logging behavior."""

    @pytest.mark.asyncio
    async def test_build_kernel_logs_exception(self, kernel_builder):
        """Test that build_kernel logs exceptions."""
        kernel_builder.chat_completion_builder.get_chat_completion_for_model.side_effect = (
            RuntimeError("Test error")
        )

        with patch.object(kernel_builder.logger, "exception") as mock_log:
            with pytest.raises(RuntimeError, match="Test error"):
                await kernel_builder.build_kernel(
                    model_name="gpt-4o",
                    service_id="test-service",
                    plugins=[],
                    remote_plugins=[],
                )

            # Should log exceptions from both _create_base_kernel and build_kernel
            assert mock_log.call_count >= 1
            # Check that the final build_kernel exception log is present
            last_call_args = str(mock_log.call_args_list[-1])
            assert "Could build kernel with service ID test-service" in last_call_args

    def test_get_model_type_logs_exception(self, kernel_builder):
        """Test that get_model_type_for_name logs exceptions."""
        kernel_builder.chat_completion_builder.get_model_type_for_name.side_effect = ValueError(
            "Model error"
        )

        with patch.object(kernel_builder.logger, "exception") as mock_log:
            with pytest.raises(ValueError, match="Model error"):
                kernel_builder.get_model_type_for_name("unknown-model")

            mock_log.assert_called_once()
            assert "Could not get model type for unknown-model" in str(mock_log.call_args)

    def test_create_base_kernel_logs_exception(self, kernel_builder):
        """Test that _create_base_kernel logs exceptions."""
        kernel_builder.chat_completion_builder.get_chat_completion_for_model.side_effect = (
            RuntimeError("Kernel error")
        )

        with patch.object(kernel_builder.logger, "exception") as mock_log:
            with pytest.raises(RuntimeError, match="Kernel error"):
                kernel_builder._create_base_kernel("gpt-4o", "test-service")

            mock_log.assert_called_once()
            assert "Could not create base kernelwith service id test-service" in str(
                mock_log.call_args
            )

    def test_load_remote_plugins_logs_exception(self, kernel_builder):
        """Test that _load_remote_plugins logs exceptions."""
        kernel = Kernel()
        kernel_builder.remote_plugin_loader.load_remote_plugins.side_effect = RuntimeError(
            "Plugin error"
        )

        with patch.object(kernel_builder.logger, "exception") as mock_log:
            with pytest.raises(RuntimeError, match="Plugin error"):
                kernel_builder._load_remote_plugins(["plugin1"], kernel)

            mock_log.assert_called_once()
            assert "Could not load remote plugings" in str(mock_log.call_args)

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_logs_warning_no_user_id(self, kernel_builder):
        """Test that _get_plugin_authorization logs warning when no user ID."""
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value=None)

        with patch.object(kernel_builder.logger, "warning") as mock_log:
            await kernel_builder._get_plugin_authorization("test_plugin", "Bearer token")

            mock_log.assert_called_once()
            assert "Could not extract user ID" in str(mock_log.call_args)

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_logs_info_cached_token(self, kernel_builder):
        """Test that _get_plugin_authorization logs info when using cached token."""
        mock_cached_auth_data = MagicMock()
        mock_cached_auth_data.access_token = "cached_token"
        kernel_builder.auth_storage_manager.retrieve.return_value = mock_cached_auth_data
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value="user123")

        with patch.object(kernel_builder.logger, "info") as mock_log:
            await kernel_builder._get_plugin_authorization("test_plugin", "Bearer token")

            mock_log.assert_called_once()
            assert "Using cached token for plugin test_plugin" in str(mock_log.call_args)

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_logs_debug_no_cached_token(self, kernel_builder):
        """Test that _get_plugin_authorization logs debug when no cached token."""
        kernel_builder.auth_storage_manager.retrieve.return_value = None
        kernel_builder.authorizer.authorize_request = AsyncMock(return_value="user123")

        with patch.object(kernel_builder.logger, "debug") as mock_log:
            await kernel_builder._get_plugin_authorization("test_plugin", "Bearer token")

            mock_log.assert_called_once()
            assert "No cached tokens found" in str(mock_log.call_args)

    @pytest.mark.asyncio
    async def test_get_plugin_authorization_logs_warning_exception(self, kernel_builder):
        """Test that _get_plugin_authorization logs warning on exception."""
        kernel_builder.authorizer.authorize_request = AsyncMock(side_effect=Exception("Test error"))

        with patch.object(kernel_builder.logger, "warning") as mock_log:
            await kernel_builder._get_plugin_authorization("test_plugin", "Bearer token")

            mock_log.assert_called_once()
            assert "Error retrieving cached tokens for plugin test_plugin" in str(
                mock_log.call_args
            )
