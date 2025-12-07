"""
MCP State Manager - Abstract Interface

Provides abstract base class for managing MCP tool discovery and session state.
Follows the same pattern as TaskPersistenceManager and SecureAuthStorageManager.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Dict, Optional


class DiscoveryError(Exception):
    """Base exception for MCP state manager errors."""
    pass


class DiscoveryCreateError(DiscoveryError):
    """Raised when state creation fails."""
    pass


class DiscoveryUpdateError(DiscoveryError):
    """Raised when state update fails."""
    pass


class McpState:
    """
    MCP state for a specific user session.

    Stores the results of MCP server discovery and session management including:
    - Which servers have been discovered
    - Serialized plugin data for each server
    - MCP session IDs for stateful servers
    - Completion status

    Scoped to (user_id, session_id) for session-level isolation.

    Structure of discovered_servers:
    {
        "server_name": {
            "tools": [...],  # Plugin metadata
            "mcp_session_id": "session-abc123",  # Optional, for stateful servers
            "last_used_at": "2025-01-15T10:30:00Z",  # Optional, session activity timestamp
            "created_at": "2025-01-15T10:00:00Z"  # Optional, session creation timestamp
        }
    }
    """

    def __init__(
        self,
        user_id: str,
        session_id: str,
        discovered_servers: Dict[str, Dict],
        discovery_completed: bool,
        created_at: Optional[datetime] = None,
        failed_servers: Optional[Dict[str, str]] = None,
        pending_elicitations: Optional[Dict[str, Dict]] = None,
    ):
        """
        Initialize MCP state.

        Args:
            user_id: User ID for authentication and scoping
            session_id: Session ID for conversation grouping
            discovered_servers: Mapping of server_name to plugin data and session info
            discovery_completed: Whether discovery has finished successfully
            created_at: Timestamp of state creation (defaults to now)
            failed_servers: Dictionary of failed servers and their error messages
        """
        self.user_id = user_id
        self.session_id = session_id
        self.discovered_servers = discovered_servers
        self.discovery_completed = discovery_completed
        self.created_at = created_at or datetime.now(timezone.utc)
        self.failed_servers = failed_servers or {}
        self.pending_elicitations = pending_elicitations or {}


class McpStateManager(ABC):
    """
    Abstract interface for MCP state management (discovery + sessions).

    Implementations must provide storage for MCP state scoped to
    (user_id, session_id) combinations. This enables:
    - Session-level tool isolation
    - Shared discovery across tasks in the same session
    - MCP session persistence for stateful servers
    - External state storage (Redis, in-memory, etc.)

    Pattern matches:
    - TaskPersistenceManager (for task state)
    - SecureAuthStorageManager (for OAuth tokens)
    """

    @abstractmethod
    async def create_discovery(self, state: McpState) -> None:
        """
        Create initial state for (user_id, session_id).

        Args:
            state: MCP state to create

        Raises:
            DiscoveryCreateError: If state already exists for this (user_id, session_id)
        """
        pass

    @abstractmethod
    async def load_discovery(
        self, user_id: str, session_id: str
    ) -> Optional[McpState]:
        """
        Load MCP state for (user_id, session_id).

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            MCP state if exists, None otherwise
        """
        pass

    @abstractmethod
    async def update_discovery(self, state: McpState) -> None:
        """
        Update existing MCP state.

        Args:
            state: Updated MCP state

        Raises:
            DiscoveryUpdateError: If state does not exist
        """
        pass

    @abstractmethod
    async def delete_discovery(self, user_id: str, session_id: str) -> None:
        """
        Delete MCP state for (user_id, session_id).

        Args:
            user_id: User ID
            session_id: Session ID
        """
        pass

    @abstractmethod
    async def mark_completed(self, user_id: str, session_id: str) -> None:
        """
        Mark discovery as completed for (user_id, session_id).

        If the state does not exist, it will be created automatically
        with an empty discovered_servers dict and discovery_completed=True.
        A warning will be logged when auto-creating.

        This operation is idempotent - calling it multiple times has the same
        effect as calling it once.

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

    # ---------- Elicitation pending helpers ----------
    @abstractmethod
    async def store_pending_elicitation(self, user_id: str, session_id: str, elicitation_id: str, data: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    async def get_pending_elicitation(self, user_id: str, session_id: str, elicitation_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    async def delete_pending_elicitation(self, user_id: str, session_id: str, elicitation_id: str) -> None:
        pass

    @abstractmethod
    async def store_mcp_session(
        self,
        user_id: str,
        session_id: str,
        server_name: str,
        mcp_session_id: str
    ) -> None:
        """
        Store MCP session ID for a server.

        If state doesn't exist, it will be created. If server doesn't exist
        in discovered_servers, it will be added.

        Args:
            user_id: User ID
            session_id: Teal agent session ID
            server_name: Name of the MCP server
            mcp_session_id: MCP session ID from server

        Raises:
            DiscoveryUpdateError: If state update fails
        """
        pass

    @abstractmethod
    async def get_mcp_session(
        self,
        user_id: str,
        session_id: str,
        server_name: str
    ) -> Optional[str]:
        """
        Get MCP session ID for a server.

        Args:
            user_id: User ID
            session_id: Teal agent session ID
            server_name: Name of the MCP server

        Returns:
            MCP session ID if exists, None otherwise
        """
        pass

    @abstractmethod
    async def update_session_last_used(
        self,
        user_id: str,
        session_id: str,
        server_name: str
    ) -> None:
        """
        Update last_used timestamp for an MCP session.

        Args:
            user_id: User ID
            session_id: Teal agent session ID
            server_name: Name of the MCP server

        Raises:
            DiscoveryUpdateError: If state or server doesn't exist
        """
        pass

    @abstractmethod
    async def clear_mcp_session(
        self,
        user_id: str,
        session_id: str,
        server_name: str,
        expected_session_id: str | None = None,
    ) -> None:
        """
        Clear the stored MCP session for a given server (if present).

        Args:
            user_id: User ID
            session_id: Teal agent session ID
            server_name: Name of the MCP server
            expected_session_id: Optional session id to match before clearing
        """
        pass
