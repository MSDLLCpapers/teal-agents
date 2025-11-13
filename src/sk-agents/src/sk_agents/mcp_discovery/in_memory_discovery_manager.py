"""
In-Memory MCP Discovery Manager

Provides in-memory implementation for development and testing.
Follows the same pattern as InMemoryPersistenceManager.
"""

import asyncio
import logging
from typing import Dict, Optional, Tuple

from sk_agents.mcp_discovery.mcp_discovery_manager import (
    McpDiscoveryManager,
    McpDiscoveryState,
)

logger = logging.getLogger(__name__)


class InMemoryDiscoveryManager(McpDiscoveryManager):
    """
    In-memory implementation of MCP discovery manager.

    Stores discovery state in memory with thread-safe access.
    Suitable for:
    - Development and testing
    - Single-instance deployments
    - Scenarios where discovery persistence is not required

    Note: State is lost on server restart.
    """

    def __init__(self, app_config):
        """
        Initialize in-memory discovery manager.

        Args:
            app_config: Application configuration (for consistency with other managers)
        """
        self.app_config = app_config
        # Storage: {(user_id, session_id): McpDiscoveryState}
        self._storage: Dict[Tuple[str, str], McpDiscoveryState] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, user_id: str, session_id: str) -> Tuple[str, str]:
        """
        Create composite key for storage.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            Tuple of (user_id, session_id)
        """
        return (user_id, session_id)

    async def create_discovery(self, state: McpDiscoveryState) -> None:
        """
        Create initial discovery state.

        Args:
            state: Discovery state to create

        Raises:
            ValueError: If state already exists
        """
        async with self._lock:
            key = self._make_key(state.user_id, state.session_id)
            if key in self._storage:
                raise ValueError(
                    f"Discovery state already exists for user={state.user_id}, "
                    f"session={state.session_id}"
                )
            self._storage[key] = state
            logger.debug(
                f"Created discovery state for user={state.user_id}, session={state.session_id}"
            )

    async def load_discovery(
        self, user_id: str, session_id: str
    ) -> Optional[McpDiscoveryState]:
        """
        Load discovery state.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            Discovery state if exists, None otherwise
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            return self._storage.get(key)

    async def update_discovery(self, state: McpDiscoveryState) -> None:
        """
        Update existing discovery state.

        Args:
            state: Updated discovery state

        Raises:
            ValueError: If state does not exist
        """
        async with self._lock:
            key = self._make_key(state.user_id, state.session_id)
            if key not in self._storage:
                raise ValueError(
                    f"Discovery state not found for user={state.user_id}, "
                    f"session={state.session_id}"
                )
            self._storage[key] = state
            logger.debug(
                f"Updated discovery state for user={state.user_id}, session={state.session_id}"
            )

    async def delete_discovery(self, user_id: str, session_id: str) -> None:
        """
        Delete discovery state.

        Args:
            user_id: User ID
            session_id: Session ID
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            if key in self._storage:
                del self._storage[key]
                logger.debug(
                    f"Deleted discovery state for user={user_id}, session={session_id}"
                )

    async def mark_completed(self, user_id: str, session_id: str) -> None:
        """
        Mark discovery as completed.

        Args:
            user_id: User ID
            session_id: Session ID
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            if key in self._storage:
                self._storage[key].discovery_completed = True
                logger.debug(
                    f"Marked discovery completed for user={user_id}, session={session_id}"
                )

    async def is_completed(self, user_id: str, session_id: str) -> bool:
        """
        Check if discovery is completed.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            True if discovery completed, False otherwise
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            state = self._storage.get(key)
            return state.discovery_completed if state else False
