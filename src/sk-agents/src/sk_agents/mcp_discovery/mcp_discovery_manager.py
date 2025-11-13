"""
MCP Discovery Manager - Abstract Interface

Provides abstract base class for managing MCP tool discovery state.
Follows the same pattern as TaskPersistenceManager and SecureAuthStorageManager.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Optional


class McpDiscoveryState:
    """
    Discovery state for a specific user session.

    Stores the results of MCP server discovery including:
    - Which servers have been discovered
    - Serialized plugin data for each server
    - Completion status

    Scoped to (user_id, session_id) for session-level isolation.
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        discovered_servers: Dict[str, Dict],
        discovery_completed: bool,
        created_at: Optional[datetime] = None,
    ):
        """
        Initialize discovery state.

        Args:
            user_id: User ID for authentication and scoping
            session_id: Session ID for conversation grouping
            discovered_servers: Mapping of server_name to serialized plugin data
            discovery_completed: Whether discovery has finished successfully
            created_at: Timestamp of state creation (defaults to now)
        """
        self.user_id = user_id
        self.session_id = session_id
        self.discovered_servers = discovered_servers
        self.discovery_completed = discovery_completed
        self.created_at = created_at or datetime.now()


class McpDiscoveryManager(ABC):
    """
    Abstract interface for MCP discovery state management.

    Implementations must provide storage for discovery state scoped to
    (user_id, session_id) combinations. This enables:
    - Session-level tool isolation
    - Shared discovery across tasks in the same session
    - External state storage (Redis, in-memory, etc.)

    Pattern matches:
    - TaskPersistenceManager (for task state)
    - SecureAuthStorageManager (for OAuth tokens)
    """

    @abstractmethod
    async def create_discovery(self, state: McpDiscoveryState) -> None:
        """
        Create initial discovery state for (user_id, session_id).

        Args:
            state: Discovery state to create

        Raises:
            ValueError: If state already exists for this (user_id, session_id)
        """
        pass

    @abstractmethod
    async def load_discovery(
        self, user_id: str, session_id: str
    ) -> Optional[McpDiscoveryState]:
        """
        Load discovery state for (user_id, session_id).

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            Discovery state if exists, None otherwise
        """
        pass

    @abstractmethod
    async def update_discovery(self, state: McpDiscoveryState) -> None:
        """
        Update existing discovery state.

        Args:
            state: Updated discovery state

        Raises:
            ValueError: If state does not exist
        """
        pass

    @abstractmethod
    async def delete_discovery(self, user_id: str, session_id: str) -> None:
        """
        Delete discovery state for (user_id, session_id).

        Args:
            user_id: User ID
            session_id: Session ID
        """
        pass

    @abstractmethod
    async def mark_completed(self, user_id: str, session_id: str) -> None:
        """
        Mark discovery as completed for (user_id, session_id).

        Args:
            user_id: User ID
            session_id: Session ID
        """
        pass

    @abstractmethod
    async def is_completed(self, user_id: str, session_id: str) -> bool:
        """
        Check if discovery is completed for (user_id, session_id).

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            True if discovery completed, False otherwise
        """
        pass
