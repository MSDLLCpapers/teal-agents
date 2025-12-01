"""
Direct agent client for FileAssistant.

This module provides a direct interface to the TealAgentsV1Alpha1Handler,
bypassing the FastAPI layer for CLI usage.
"""

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import AsyncIterator, Optional

from dotenv import load_dotenv
from pydantic_yaml import parse_yaml_file_as

from ska_utils import AppConfig
from sk_agents.persistence.in_memory_persistence_manager import InMemoryPersistenceManager
from sk_agents.ska_types import BaseConfig, ContentType, MultiModalItem
from sk_agents.tealagents.models import (
    AuthChallengeResponse,
    TealAgentsPartialResponse,
    TealAgentsResponse,
    UserMessage,
)
from sk_agents.tealagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.tealagents.kernel_builder import KernelBuilder
from sk_agents.tealagents.remote_plugin_loader import RemotePluginCatalog, RemotePluginLoader
from sk_agents.tealagents.v1alpha1.agent.handler import TealAgentsV1Alpha1Handler
from sk_agents.tealagents.v1alpha1.agent_builder import AgentBuilder


logger = logging.getLogger(__name__)


class DirectAgentClient:
    """
    Direct client for invoking TealAgentsV1Alpha1Handler without FastAPI.
    """

    def __init__(self, project_dir: Path):
        """
        Initialize the direct agent client.

        Args:
            project_dir: Path to the project directory containing config.yaml and .env
        """
        self.project_dir = project_dir
        self.config_path = project_dir / "config.yaml"
        self.env_path = project_dir / ".env"
        
        self.handler: Optional[TealAgentsV1Alpha1Handler] = None
        self.session_id: str = str(uuid.uuid4())
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the agent handler and all dependencies."""
        if self._initialized:
            logger.warning("Client already initialized")
            return

        logger.info("Initializing DirectAgentClient...")

        # Ensure project dir is on sys.path so relative plugin/factory modules resolve
        if str(self.project_dir) not in sys.path:
            sys.path.insert(0, str(self.project_dir))

        # Load environment variables FIRST
        if self.env_path.exists():
            load_dotenv(self.env_path)
            logger.info(f"Loaded environment from {self.env_path}")
        else:
            logger.warning(f"No .env file found at {self.env_path}")

        # Register platform configs first (from sk_agents.configs)
        from sk_agents.configs import configs as platform_configs
        AppConfig.add_configs(platform_configs)
        logger.info("Registered platform configs")

        # Register custom factory configs if provided
        factory_module = os.getenv("TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE")
        factory_class = os.getenv("TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME")
        if factory_module and factory_class:
            # Ensure relative path resolves from project_dir
            if not os.path.isabs(factory_module):
                factory_module = str((self.project_dir / factory_module).resolve())
                os.environ["TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE"] = factory_module
            try:
                module = __import__(
                    Path(factory_module).stem.replace(".py", ""),
                    globals(),
                    locals(),
                    [factory_class],
                )
                MerckChatCompletionFactory = getattr(module, factory_class)
                factory_configs = MerckChatCompletionFactory.get_configs()
                if factory_configs:
                    AppConfig.add_configs(factory_configs)
                logger.info("Registered custom ChatCompletionFactory configs")
            except Exception as e:
                logger.error(f"Failed to load custom ChatCompletionFactory: {e}")
                raise
        else:
            logger.info("No custom ChatCompletionFactory configured; using default")

        # Load config.yaml
        if not self.config_path.exists():
            raise FileNotFoundError(f"Config file not found: {self.config_path}")

        config: BaseConfig = parse_yaml_file_as(BaseConfig, self.config_path)
        logger.info(f"Loaded config: {config.name} v{config.version}")

        # Get AppConfig instance (already created by add_configs)
        app_config = AppConfig()

        # Initialize plugin loader with custom plugin module
        from sk_agents.plugin_loader import get_plugin_loader
        plugin_module_path = app_config.get("TA_PLUGIN_MODULE")
        if plugin_module_path:
            # Resolve relative plugin module to project directory
            if not os.path.isabs(plugin_module_path):
                plugin_module_path = str((self.project_dir / plugin_module_path).resolve())
                app_config.props["TA_PLUGIN_MODULE"] = plugin_module_path
            plugin_loader = get_plugin_loader(plugin_module_path)
            logger.info(f"Initialized plugin loader with: {plugin_module_path}")
        else:
            logger.warning("TA_PLUGIN_MODULE not configured")

        # Create persistence manager
        state_manager = InMemoryPersistenceManager()
        logger.info("Created InMemoryPersistenceManager")

        # Create MCP discovery manager if MCP servers configured
        agent_config_spec = config.spec.get("agent") if config.spec else None
        mcp_servers = agent_config_spec.get("mcp_servers", []) if agent_config_spec else []

        discovery_manager = None
        if mcp_servers and len(mcp_servers) > 0:
            from sk_agents.mcp_discovery import DiscoveryManagerFactory

            discovery_factory = DiscoveryManagerFactory(app_config)
            discovery_manager = discovery_factory.get_discovery_manager()
            logger.info(f"Created MCP discovery manager for {len(mcp_servers)} servers")
        else:
            logger.info("No MCP servers configured, skipping discovery manager")

        # Create chat completion builder (which loads custom factory if configured)
        chat_completion_builder = ChatCompletionBuilder(app_config)
        logger.info("Created ChatCompletionBuilder")

        # Create remote plugin loader
        remote_plugin_catalog = RemotePluginCatalog(app_config)
        remote_plugin_loader = RemotePluginLoader(remote_plugin_catalog)
        logger.info("Created RemotePluginLoader")

        # Create authorization (dummy for testing)
        authorization = None  # Will use DummyAuthorizer internally

        # Create KernelBuilder
        kernel_builder = KernelBuilder(
            chat_completion_builder=chat_completion_builder,
            remote_plugin_loader=remote_plugin_loader,
            app_config=app_config,
            authorization=authorization,
        )
        logger.info("Created KernelBuilder")

        # Create AgentBuilder
        agent_builder = AgentBuilder(
            kernel_builder=kernel_builder,
            authorization=authorization,
        )
        logger.info("Created AgentBuilder")

        # Create Handler
        self.handler = TealAgentsV1Alpha1Handler(
            config=config,
            app_config=app_config,
            agent_builder=agent_builder,
            state_manager=state_manager,
            discovery_manager=discovery_manager,
        )
        logger.info("Created TealAgentsV1Alpha1Handler")

        # Debug: Log what plugins are configured
        agent_config_spec = config.spec.get("agent") if config.spec else None
        if agent_config_spec:
            plugins_configured = agent_config_spec.get("plugins", [])
            logger.info(f"Plugins configured in config.yaml: {plugins_configured}")
        
        self._initialized = True
        logger.info("DirectAgentClient initialization complete")

    async def chat(
        self,
        message: str,
        task_id: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """
        Send a message to the agent and stream the response.

        Args:
            message: User message
            task_id: Optional task ID (will create new if not provided)

        Yields:
            Response chunks as they arrive
        """
        if not self._initialized or not self.handler:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        # Create task ID if not provided
        if not task_id:
            task_id = str(uuid.uuid4())

        # Create UserMessage
        user_message = UserMessage(
            task_id=task_id,
            session_id=self.session_id,
            items=[
                MultiModalItem(
                    content_type=ContentType.TEXT,
                    content=message,
                )
            ],
        )

        # Dummy auth token (DummyAuthorizer will accept anything)
        auth_token = "dummy_token"

        try:
            # Stream response from handler
            async for response_chunk in self.handler.invoke_stream(auth_token, user_message):
                if isinstance(response_chunk, TealAgentsPartialResponse):
                    # Partial response - stream the content
                    if response_chunk.output_partial:
                        yield response_chunk.output_partial
                elif isinstance(response_chunk, TealAgentsResponse):
                    # Final response - already accumulated from partials, don't re-yield
                    # Just log completion (output was already streamed via partials)
                    logger.debug(f"Received final response (already streamed via partials)")
                elif isinstance(response_chunk, AuthChallengeResponse):
                    # Authentication required - format and display auth challenges
                    yield "\n🔐 **Authentication Required**\n\n"
                    yield f"{response_chunk.message}\n\n"

                    for challenge in response_chunk.auth_challenges:
                        server_name = challenge.get("server_name", "Unknown")
                        auth_server = challenge.get("auth_server", "")
                        scopes = challenge.get("scopes", [])
                        auth_url = challenge.get("auth_url", "")

                        yield f"**MCP Server:** `{server_name}`\n\n"

                        if auth_url:
                            yield "**Please complete OAuth2 flow:**\n\n"
                            yield f"1. Visit: {auth_url}\n"
                            yield f"2. Authorize the application\n"
                            yield f"3. Return here and retry your request\n\n"

                        if auth_server:
                            yield f"**Auth Server:** {auth_server}\n"
                        if scopes:
                            yield f"**Scopes:** {', '.join(scopes)}\n"

                        yield "\n"

                    yield "---\n\n"
                    yield "After completing authentication, please send your message again.\n"
                # Note: We're ignoring HitlResponse for now

        except Exception as e:
            logger.error(f"Error during chat: {e}", exc_info=True)
            yield f"\n❌ Error: {str(e)}\n"

    def new_session(self) -> str:
        """
        Create a new session ID.

        Returns:
            New session ID
        """
        self.session_id = str(uuid.uuid4())
        logger.info(f"Created new session: {self.session_id}")
        return self.session_id

    async def get_available_tools(self, session_id: str | None = None) -> dict[str, list[dict]]:
        """
        Get all available tools from registered plugins.

        Args:
            session_id: Optional session ID to include MCP plugins for this session

        Returns:
            Dictionary mapping plugin names to their tools with metadata
        """
        if not self._initialized or not self.handler:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        # Build a temporary kernel to inspect tools
        # self.handler.config is already a Config object
        agent_config = self.handler.config.get_agent()

        # Build agent first (without MCP plugins)
        dummy_auth = "dummyuser"
        agent = await self.handler.agent_builder.build_agent(
            agent_config,
            extra_data_collector=None,
            user_id=dummy_auth
        )

        # Load MCP plugins after agent construction if session_id provided
        # This follows the same pattern as handler.py
        if session_id and agent_config.mcp_servers and self.handler.discovery_manager:
            await self.handler.agent_builder.kernel_builder.load_mcp_plugins(
                agent.agent.kernel,
                dummy_auth,
                session_id,
                self.handler.discovery_manager
            )

        kernel = agent.agent.kernel
        
        # Extract plugin information
        tools_by_plugin = {}
        
        for plugin_name in kernel.plugins.keys():
            plugin = kernel.plugins[plugin_name]
            tools = []
            
            # Get functions from the plugin
            # plugin.functions is a dict of function_name -> KernelFunction
            if hasattr(plugin, 'functions'):
                for function_name, func in plugin.functions.items():
                    # Get function metadata
                    tool_info = {
                        "name": function_name,
                        "description": func.description or "No description available",
                        "parameters": []
                    }
                    
                    # Extract parameter information if available
                    if hasattr(func, "metadata") and func.metadata:
                        if hasattr(func.metadata, "parameters"):
                            for param in func.metadata.parameters:
                                tool_info["parameters"].append({
                                    "name": param.name,
                                    "description": param.description or "",
                                    "required": param.is_required,
                                    "type": param.type_,
                                })
                    
                    tools.append(tool_info)
            
            if tools:
                tools_by_plugin[plugin_name] = tools
        
        return tools_by_plugin

    async def call_tool(self, plugin_name: str, function_name: str, session_id: str | None = None, **kwargs) -> str:
        """
        Directly call a tool function.

        Args:
            plugin_name: Name of the plugin
            function_name: Name of the function to call
            session_id: Optional session ID to include MCP plugins for this session
            **kwargs: Arguments to pass to the function

        Returns:
            String result from the tool
        """
        if not self._initialized or not self.handler:
            raise RuntimeError("Client not initialized. Call initialize() first.")

        try:
            # Build a temporary kernel to call the tool
            from semantic_kernel.functions.kernel_arguments import KernelArguments

            # self.handler.config is already a Config object
            agent_config = self.handler.config.get_agent()

            # Build agent first (without MCP plugins)
            dummy_auth = "dummyuser"
            agent = await self.handler.agent_builder.build_agent(
                agent_config,
                extra_data_collector=None,
                user_id=dummy_auth
            )

            # Load MCP plugins after agent construction if session_id provided
            # This follows the same pattern as handler.py and get_available_tools()
            if session_id and agent_config.mcp_servers and self.handler.discovery_manager:
                await self.handler.agent_builder.kernel_builder.load_mcp_plugins(
                    agent.agent.kernel,
                    dummy_auth,
                    session_id,
                    self.handler.discovery_manager
                )

            kernel = agent.agent.kernel
            
            # Get the function
            function = kernel.get_function(plugin_name, function_name)
            
            # Create kernel arguments
            kernel_args = KernelArguments(**kwargs)
            
            # Invoke the function
            result = await function.invoke(kernel, kernel_args)
            
            # Return the result as string
            return str(result)
            
        except Exception as e:
            logger.error(f"Error calling tool {plugin_name}.{function_name}: {e}", exc_info=True)
            raise

    @property
    def is_initialized(self) -> bool:
        """Check if client is initialized."""
        return self._initialized


__all__ = ["DirectAgentClient"]
