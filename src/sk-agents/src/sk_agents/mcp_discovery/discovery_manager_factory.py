"""
MCP Discovery Manager Factory

Provides singleton factory for creating MCP discovery manager instances
with dynamic module loading and dependency injection.

Follows the same pattern as PersistenceFactory and AuthStorageFactory.
"""

import logging
from typing import Optional

from ska_utils import AppConfig

from sk_agents.singleton_metaclass import SingletonMeta

logger = logging.getLogger(__name__)


class DiscoveryManagerFactory(metaclass=SingletonMeta):
    """
    Factory for MCP discovery manager with dependency injection.

    Uses singleton pattern to ensure only one factory instance exists.
    Dynamically loads discovery manager implementation based on
    environment variables.

    Configuration:
        TA_MCP_DISCOVERY_MODULE: Python module containing manager class
        TA_MCP_DISCOVERY_CLASS: Manager class name

    Defaults to InMemoryDiscoveryManager for development.
    """

    def __init__(self, app_config: AppConfig):
        """
        Initialize factory with app configuration.

        Args:
            app_config: Application configuration for env vars
        """
        self.app_config = app_config
        self._manager: Optional["McpDiscoveryManager"] = None  # noqa: F821

    def get_discovery_manager(self) -> "McpDiscoveryManager":  # noqa: F821
        """
        Get discovery manager instance (cached singleton).

        Loads manager implementation on first call based on configuration,
        then caches for subsequent calls.

        Returns:
            McpDiscoveryManager instance

        Raises:
            Exception: If manager class cannot be loaded (falls back to in-memory)
        """
        if self._manager is None:
            # Import here to avoid circular dependency
            from sk_agents.configs import TA_MCP_DISCOVERY_CLASS, TA_MCP_DISCOVERY_MODULE

            module_name = self.app_config.get(
                TA_MCP_DISCOVERY_MODULE.env_name,
                default="sk_agents.mcp_discovery.in_memory_discovery_manager",
            )
            class_name = self.app_config.get(
                TA_MCP_DISCOVERY_CLASS.env_name, default="InMemoryDiscoveryManager"
            )

            try:
                # Dynamic module loading
                module = __import__(module_name, fromlist=[class_name])
                manager_class = getattr(module, class_name)
                self._manager = manager_class(self.app_config)
                logger.info(f"Initialized MCP discovery manager: {class_name}")

            except Exception as e:
                logger.error(
                    f"Failed to load discovery manager {class_name} from {module_name}: {e}. "
                    f"Falling back to InMemoryDiscoveryManager"
                )

                # Fallback to in-memory implementation
                try:
                    from sk_agents.mcp_discovery.in_memory_discovery_manager import (
                        InMemoryDiscoveryManager,
                    )

                    self._manager = InMemoryDiscoveryManager(self.app_config)
                    logger.info("Fallback to InMemoryDiscoveryManager successful")

                except Exception as fallback_error:
                    logger.critical(
                        f"Failed to load fallback InMemoryDiscoveryManager: {fallback_error}"
                    )
                    raise

        return self._manager
