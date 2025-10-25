import asyncio
import logging
from typing import TYPE_CHECKING

from semantic_kernel.kernel import Kernel
from ska_utils import AppConfig

from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.secure_auth_storage_manager import SecureAuthStorageManager
from sk_agents.authorization.authorizer_factory import AuthorizerFactory
from sk_agents.authorization.request_authorizer import RequestAuthorizer
from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.plugin_loader import get_plugin_loader
from sk_agents.ska_types import ModelType
from sk_agents.tealagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.tealagents.remote_plugin_loader import RemotePluginLoader
from sk_agents.tealagents.v1alpha1.config import McpServerConfig


class KernelBuilder:
    def __init__(
        self,
        chat_completion_builder: ChatCompletionBuilder,
        remote_plugin_loader: RemotePluginLoader,
        app_config: AppConfig,
        authorization: str | None = None,
    ):
        self.chat_completion_builder: ChatCompletionBuilder = chat_completion_builder
        self.remote_plugin_loader = remote_plugin_loader
        self.app_config: AppConfig = app_config
        self.authorization = authorization
        self.logger = logging.getLogger(__name__)

        # Initialize auth storage and authorizer for token cache functionality
        self.auth_storage_manager: SecureAuthStorageManager = AuthStorageFactory(
            app_config
        ).get_auth_storage_manager()
        self.authorizer: RequestAuthorizer = AuthorizerFactory(app_config).get_authorizer()

    async def build_kernel(
        self,
        model_name: str,
        service_id: str,
        plugins: list[str],
        remote_plugins: list[str],
        mcp_servers: list[McpServerConfig] | None = None,
        authorization: str | None = None,
        extra_data_collector: ExtraDataCollector | None = None,
        user_id: str | None = None,
    ) -> Kernel:
        try:
            kernel = self._create_base_kernel(model_name, service_id)
            kernel = self._parse_plugins(plugins, kernel, authorization, extra_data_collector)
            kernel = self._load_remote_plugins(remote_plugins, kernel)
            
            # MCP plugins will be loaded separately in async context by handler
            # Remove sync MCP loading to avoid event loop conflicts
            
            return kernel
        except Exception as e:
            self.logger.exception(f"Could build kernel with service ID {service_id}. - {e}")
            raise

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        try:
            return self.chat_completion_builder.get_model_type_for_name(model_name)
        except Exception as e:
            self.logger.exception(f"Could not get model type for {model_name}. - {e}")
            raise

    def model_supports_structured_output(self, model_name: str) -> bool:
        return self.chat_completion_builder.model_supports_structured_output(model_name)

    def _create_base_kernel(self, model_name: str, service_id: str) -> Kernel:
        try:
            chat_completion = self.chat_completion_builder.get_chat_completion_for_model(
                service_id=service_id,
                model_name=model_name,
            )

            kernel = Kernel()
            kernel.add_service(chat_completion)

            return kernel
        except Exception as e:
            self.logger.exception(f"Could not create base kernelwith service id {service_id}.-{e}")
            raise

    def _load_remote_plugins(self, remote_plugins: list[str], kernel: Kernel) -> Kernel:
        if remote_plugins is None or len(remote_plugins) < 1:
            return kernel
        try:
            self.remote_plugin_loader.load_remote_plugins(kernel, remote_plugins)
            return kernel
        except Exception as e:
            self.logger.exception(f"Could not load remote plugings. -{e}")
            raise

    async def load_mcp_plugins(self, mcp_servers: list[McpServerConfig] | None, kernel: Kernel, user_id: str | None = None, session_id: str | None = None) -> Kernel:
        """
        Load MCP plugins by instantiating them from the plugin registry.

        This mirrors the non-MCP plugin pattern:
        1. Get plugin CLASS from registry (like loading from file)
        2. Instantiate plugin
        3. Register with kernel

        Note: MCP tools must be discovered first via McpPluginRegistry.discover_and_materialize()
        at session start.
        """
        if mcp_servers is None or len(mcp_servers) < 1:
            return kernel

        if not user_id:
            raise ValueError("user_id is required when loading MCP plugins")

        try:
            from sk_agents.mcp_plugin_registry import McpPluginRegistry

            for server_config in mcp_servers:
                # Get MCP plugin class from registry (like loading from file for non-MCP)
                plugin_class = McpPluginRegistry.get_plugin_class(server_config.name)

                if plugin_class is None:
                    self.logger.warning(
                        f"MCP plugin class for {server_config.name} not found in registry. "
                        f"Ensure McpPluginRegistry.discover_and_materialize() was called at session start."
                    )
                    continue

                # Instantiate plugin (same pattern as non-MCP!)
                # Note: authorization passed from handler, extra_data_collector from context
                plugin_instance = plugin_class(
                    user_id=user_id,
                    authorization=self.authorization,
                    extra_data_collector=None  # Can be passed if needed
                )

                # Register with kernel (same pattern as non-MCP!)
                kernel.add_plugin(plugin_instance, f"mcp_{server_config.name}")
                self.logger.info(f"Registered MCP plugin instance for server: {server_config.name}")

            return kernel

        except Exception as e:
            self.logger.exception(f"Could not load MCP plugins. - {e}")
            raise

    def _parse_plugins(
        self,
        plugin_names: list[str],
        kernel: Kernel,
        authorization: str | None = None,
        extra_data_collector: ExtraDataCollector | None = None,
    ) -> Kernel:
        if plugin_names is None or len(plugin_names) < 1:
            return kernel

        plugin_loader = get_plugin_loader()
        plugins = plugin_loader.get_plugins(plugin_names)

        for plugin_name, plugin_class in plugins.items():
            # For non-MCP plugins, use original authorization directly
            # (MCP plugins handle auth differently via user_id)
            plugin_authorization = authorization

            # Create and add the plugin to the kernel
            kernel.add_plugin(plugin_class(plugin_authorization, extra_data_collector), plugin_name)

        return kernel

    async def _get_plugin_authorization(
        self, plugin_name: str, original_authorization: str | None = None
    ) -> str | None:
        """
        Get plugin-specific authorization, checking token cache for stored OAuth2 tokens.

        Args:
            plugin_name: Name of the plugin requesting authorization
            original_authorization: Original authorization header from the request

        Returns:
            Authorization string to use for the plugin (either cached token or original)
        """
        if not original_authorization:
            return None

        try:
            # Extract user ID from the authorization header
            user_id = await self.authorizer.authorize_request(original_authorization)
            if not user_id:
                self.logger.warning(
                    f"Could not extract user ID from authorization for plugin {plugin_name}"
                )
                return original_authorization

            # Try to retrieve cached OAuth2 tokens for this user and plugin
            cached_auth_data = self.auth_storage_manager.retrieve(user_id, plugin_name)

            if cached_auth_data and hasattr(cached_auth_data, "access_token"):
                self.logger.info(f"Using cached token for plugin {plugin_name}, user {user_id}")
                # Return the cached access token in Bearer format
                return f"Bearer {cached_auth_data.access_token}"
            else:
                self.logger.debug(
                    f"No cached tokens found for plugin {plugin_name}, user {user_id} - "
                    f"returning None"
                )
                return None

        except Exception as e:
            self.logger.warning(
                f"Error retrieving cached tokens for plugin {plugin_name}: {e} - returning None"
            )
            return None
