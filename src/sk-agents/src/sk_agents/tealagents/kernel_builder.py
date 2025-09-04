import asyncio
import logging

from semantic_kernel.kernel import Kernel
from ska_utils import AppConfig

from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.mcp_client import get_mcp_client
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

    def build_kernel(
        self,
        model_name: str,
        service_id: str,
        plugins: list[str],
        remote_plugins: list[str],
        mcp_servers: list[McpServerConfig] | None = None,
        authorization: str | None = None,
        extra_data_collector: ExtraDataCollector | None = None,
    ) -> Kernel:
        try:
            kernel = self._create_base_kernel(model_name, service_id)
            kernel = self._parse_plugins(plugins, kernel, authorization, extra_data_collector)
            kernel = self._load_remote_plugins(remote_plugins, kernel)
            kernel = asyncio.run(self._load_mcp_plugins(mcp_servers, kernel))
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

    async def _load_mcp_plugins(self, mcp_servers: list[McpServerConfig] | None, kernel: Kernel) -> Kernel:
        """Load MCP plugins by connecting to MCP servers and registering their tools."""
        if mcp_servers is None or len(mcp_servers) < 1:
            return kernel
        
        try:
            mcp_client = get_mcp_client()
            
            for server_config in mcp_servers:
                try:
                    self.logger.info(f"Connecting to MCP server: {server_config.name}")
                    await mcp_client.connect_server(server_config)
                    
                    # Get the plugin for this server and register it with the kernel
                    plugin = mcp_client.get_plugin(server_config.name)
                    if plugin:
                        kernel.add_plugin(plugin, f"mcp_{server_config.name}")
                        self.logger.info(f"Registered MCP plugin for server: {server_config.name}")
                    else:
                        self.logger.warning(f"No plugin created for MCP server: {server_config.name}")
                        
                except Exception as e:
                    self.logger.error(f"Failed to load MCP server {server_config.name}: {e}")
                    # Continue with other servers rather than failing completely
                    continue
            
            return kernel
            
        except Exception as e:
            self.logger.exception(f"Could not load MCP plugins. - {e}")
            raise

    @staticmethod
    def _parse_plugins(
        plugin_names: list[str],
        kernel: Kernel,
        authorization: str | None = None,
        extra_data_collector: ExtraDataCollector | None = None,
    ) -> Kernel:
        if plugin_names is None or len(plugin_names) < 1:
            return kernel

        plugin_loader = get_plugin_loader()
        plugins = plugin_loader.get_plugins(plugin_names)
        for k, v in plugins.items():
            kernel.add_plugin(v(authorization, extra_data_collector), k)
        return kernel
