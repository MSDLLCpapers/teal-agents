"""
In-Memory MCP State Manager

Provides in-memory implementation for development and testing.
Follows the same pattern as InMemoryPersistenceManager.
"""

import asyncio
import copy
import logging
from datetime import UTC, datetime

from sk_agents.mcp_discovery.mcp_discovery_manager import (
    DiscoveryCreateError,
    DiscoveryUpdateError,
    McpState,
    McpStateManager,
)

logger = logging.getLogger(__name__)


class InMemoryStateManager(McpStateManager):
    """
    In-memory implementation of MCP state manager.

    Stores MCP state in memory with thread-safe access.
    Suitable for:
    - Development and testing
    - Single-instance deployments
    - Scenarios where persistence is not required

    Note: State is lost on server restart.
    """

    def __init__(self, app_config):
        """
        Initialize in-memory state manager.

        Args:
            app_config: Application configuration (for consistency with other managers)
        """
        self.app_config = app_config
        # Storage: {(user_id, session_id): McpState}
        self._storage: dict[tuple[str, str], McpState] = {}
        self._lock = asyncio.Lock()

    def _make_key(self, user_id: str, session_id: str) -> tuple[str, str]:
        """
        Create composite key for storage.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            Tuple of (user_id, session_id)
        """
        return (user_id, session_id)

    async def create_discovery(self, state: McpState) -> None:
        """
        Create initial MCP state.

        Args:
            state: MCP state to create

        Raises:
            DiscoveryCreateError: If state already exists
        """
        async with self._lock:
            key = self._make_key(state.user_id, state.session_id)
            if key in self._storage:
                raise DiscoveryCreateError(
                    f"MCP state already exists for user={state.user_id}, session={state.session_id}"
                )
            self._storage[key] = state
            logger.debug(f"Created MCP state for user={state.user_id}, session={state.session_id}")

    async def load_discovery(self, user_id: str, session_id: str) -> McpState | None:
        """
        Load MCP state.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            Deep copy of MCP state if exists, None otherwise.
            Returns a copy to prevent external mutations.
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            state = self._storage.get(key)
            if state is None:
                return None
            # Return deep copy to prevent external mutations bypassing update_discovery
            return copy.deepcopy(state)

    async def update_discovery(self, state: McpState) -> None:
        """
        Update existing MCP state.

        Args:
            state: Updated MCP state

        Raises:
            DiscoveryUpdateError: If state does not exist
        """
        async with self._lock:
            key = self._make_key(state.user_id, state.session_id)
            if key not in self._storage:
                raise DiscoveryUpdateError(
                    f"MCP state not found for user={state.user_id}, session={state.session_id}"
                )
            self._storage[key] = state
            logger.debug(f"Updated MCP state for user={state.user_id}, session={state.session_id}")

    async def delete_discovery(self, user_id: str, session_id: str) -> None:
        """
        Delete MCP state.

        Args:
            user_id: User ID
            session_id: Session ID
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            if key in self._storage:
                del self._storage[key]
                logger.debug(f"Deleted MCP state for user={user_id}, session={session_id}")

    async def mark_completed(self, user_id: str, session_id: str) -> None:
        """
        Mark discovery as completed.

        If state doesn't exist, auto-creates it with discovery_completed=True
        and empty discovered_servers dict. A warning is logged when auto-creating.

        Args:
            user_id: User ID
            session_id: Session ID
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            if key in self._storage:
                self._storage[key].discovery_completed = True
                logger.debug(f"Marked discovery completed for user={user_id}, session={session_id}")
            else:
                # Auto-create state if it doesn't exist
                logger.warning(
                    f"MCP state not found for user={user_id}, session={session_id}. "
                    f"Auto-creating with discovery_completed=True."
                )
                state = McpState(
                    user_id=user_id,
                    session_id=session_id,
                    discovered_servers={},
                    discovery_completed=True,
                    created_at=datetime.now(UTC),
                )
                self._storage[key] = state

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

    async def store_mcp_session(
        self, user_id: str, session_id: str, server_name: str, mcp_session_id: str
    ) -> None:
        """
        Store MCP session ID for a server.

        Args:
            user_id: User ID
            session_id: Teal agent session ID
            server_name: Name of the MCP server
            mcp_session_id: MCP session ID from server
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            state = self._storage.get(key)

            # Auto-create state if doesn't exist
            if not state:
                logger.warning(
                    f"MCP state not found for user={user_id}, session={session_id}. "
                    f"Auto-creating to store session for {server_name}."
                )
                state = McpState(
                    user_id=user_id,
                    session_id=session_id,
                    discovered_servers={},
                    discovery_completed=False,
                    created_at=datetime.now(UTC),
                )
                self._storage[key] = state

            # Ensure server entry exists and preserve plugin_data if present
            existing_entry = state.discovered_servers.get(server_name, {})
            plugin_data = existing_entry.get("plugin_data")
            state.discovered_servers[server_name] = {
                "plugin_data": plugin_data,
                **(
                    {"session": existing_entry.get("session")}
                    if existing_entry.get("session")
                    else {}
                ),
            }

            # Store session data
            session_bucket = state.discovered_servers[server_name].get("session", {})
            now_iso = datetime.now(UTC).isoformat()
            session_bucket.update(
                {
                    "mcp_session_id": mcp_session_id,
                    "created_at": session_bucket.get("created_at", now_iso),
                    "last_used_at": now_iso,
                }
            )
            state.discovered_servers[server_name]["session"] = session_bucket

            logger.debug(
                f"Stored MCP session {mcp_session_id} for server={server_name}, "
                f"user={user_id}, session={session_id}"
            )

    async def get_mcp_session(self, user_id: str, session_id: str, server_name: str) -> str | None:
        """
        Get MCP session ID for a server.

        Args:
            user_id: User ID
            session_id: Teal agent session ID
            server_name: Name of the MCP server

        Returns:
            MCP session ID if exists, None otherwise
        """
        async with self._lock:
            key = self._make_key(user_id, session_id)
            state = self._storage.get(key)

            if not state:
                return None

            server_data = state.discovered_servers.get(server_name)
            if not server_data:
                return None

            session_bucket = server_data.get("session")
            if not session_bucket:
                return None
            return session_bucket.get("mcp_session_id")

    async def update_session_last_used(
        self, user_id: str, session_id: str, server_name: str
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
        async with self._lock:
            key = self._make_key(user_id, session_id)
            state = self._storage.get(key)

            if not state:
                raise DiscoveryUpdateError(
                    f"MCP state not found for user={user_id}, session={session_id}"
                )

            if server_name not in state.discovered_servers:
                raise DiscoveryUpdateError(
                    f"Server {server_name} not found in state for "
                    f"user={user_id}, session={session_id}"
                )

            session_bucket = state.discovered_servers[server_name].get("session")
            if not session_bucket:
                session_bucket = {}
            session_bucket["last_used_at"] = datetime.now(UTC).isoformat()
            state.discovered_servers[server_name]["session"] = session_bucket

            logger.debug(
                f"Updated last_used for server={server_name}, user={user_id}, session={session_id}"
            )

    async def clear_mcp_session(
        self,
        user_id: str,
        session_id: str,
        server_name: str,
        expected_session_id: str | None = None,
    ) -> None:
        """Remove stored MCP session info for a server if present."""
        async with self._lock:
            key = self._make_key(user_id, session_id)
            state = self._storage.get(key)
            if not state:
                return
            entry = state.discovered_servers.get(server_name)
            if not entry:
                return
            if "session" in entry:
                if expected_session_id:
                    current = entry.get("session", {}).get("mcp_session_id")
                    if current and current != expected_session_id:
                        # Another session already replaced it; do not clear
                        return
                entry.pop("session", None)
                state.discovered_servers[server_name] = entry
                logger.debug(
                    f"Cleared MCP session for server={server_name}, "
                    f"user={user_id}, session={session_id}"
                )
