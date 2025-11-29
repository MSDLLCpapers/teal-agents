"""
MCP State Manager Factory

Provides singleton factory for creating MCP state manager instances
with dynamic module loading and dependency injection.

Follows the same pattern as PersistenceFactory and AuthStorageFactory.
"""

import logging
from typing import Optional

from ska_utils import AppConfig, Singleton

logger = logging.getLogger(__name__)


class DiscoveryManagerFactory(metaclass=Singleton):
    """
    Factory for MCP state manager with dependency injection.

    Uses singleton pattern to ensure only one factory instance exists.
    Dynamically loads state manager implementation based on
    environment variables.

    Configuration:
        TA_MCP_DISCOVERY_MODULE: Python module containing manager class
        TA_MCP_DISCOVERY_CLASS: Manager class name

    Defaults to InMemoryStateManager for development.
    """

    def __init__(self, app_config: AppConfig):
        """
        Initialize factory with app configuration.

        Args:
            app_config: Application configuration for env vars
        """
        self.app_config = app_config
        self._manager: Optional["McpStateManager"] = None  # noqa: F821

    def get_discovery_manager(self) -> "McpStateManager":  # noqa: F821
        """
        Get state manager instance (cached singleton).

        Loads manager implementation on first call based on configuration,
        then caches for subsequent calls.

        Returns:
            McpStateManager instance

        Raises:
            Exception: If manager class cannot be loaded (falls back to in-memory)
        """
        if self._manager is None:
            # Import here to avoid circular dependency
            from sk_agents.configs import TA_MCP_DISCOVERY_CLASS, TA_MCP_DISCOVERY_MODULE

            module_name = self.app_config.get(TA_MCP_DISCOVERY_MODULE.env_name)
            class_name = self.app_config.get(TA_MCP_DISCOVERY_CLASS.env_name)

            try:
                # Dynamic module loading
                module = __import__(module_name, fromlist=[class_name])
                manager_class = getattr(module, class_name)
                self._manager = manager_class(self.app_config)
                logger.info(f"Initialized MCP state manager: {class_name}")

            except Exception as e:
                logger.error(
                    f"Failed to load state manager {class_name} from {module_name}: {e}. "
                    f"Falling back to InMemoryStateManager"
                )

                # Fallback to in-memory implementation
                try:
                    from sk_agents.mcp_discovery.in_memory_discovery_manager import (
                        InMemoryStateManager,
                    )

                    self._manager = InMemoryStateManager(self.app_config)
                    logger.info("Fallback to InMemoryStateManager successful")

                except Exception as fallback_error:
                    logger.critical(
                        f"Failed to load fallback InMemoryStateManager: {fallback_error}"
                    )
                    raise

        return self._manager
