"""
Redis MCP State Manager

Provides Redis-backed implementation for production deployments.
Follows the same pattern as Redis persistence and auth storage.
"""

import json
import logging
from datetime import UTC, datetime

from redis.asyncio import Redis
from ska_utils import AppConfig, strtobool

from sk_agents.mcp_discovery.mcp_discovery_manager import (
    DiscoveryCreateError,
    DiscoveryUpdateError,
    McpState,
    McpStateManager,
)

logger = logging.getLogger(__name__)


class RedisStateManager(McpStateManager):
    """
    Redis-backed implementation of MCP state manager.

    Stores MCP state in Redis for:
    - Production deployments
    - Multi-instance horizontal scaling
    - Persistence across server restarts
    - Shared state across distributed systems

    Uses the same Redis configuration as other components (TA_REDIS_*).
    """

    def __init__(self, app_config: AppConfig, redis_client: Redis | None = None):
        """
        Initialize Redis state manager.

        Args:
            app_config: Application configuration for Redis connection
            redis_client: Optional pre-configured Redis client (for testing)
        """
        self.app_config = app_config
        self.redis = redis_client or self._create_redis_client()
        self.key_prefix = "mcp_state"

        # TTL support: Default to 24 hours (86400 seconds)
        from sk_agents.configs import TA_REDIS_TTL

        ttl_str = self.app_config.get(TA_REDIS_TTL.env_name)
        if ttl_str:
            self.ttl = int(ttl_str)
        else:
            # Default to 24 hours for discovery state
            self.ttl = 86400

        logger.debug(f"Redis state manager initialized with TTL={self.ttl}s")

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self.redis:
            await self.redis.close()
            logger.debug("Redis state manager connection closed")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()

    def _create_redis_client(self) -> Redis:
        """
        Create Redis client from app configuration.

        Reuses existing TA_REDIS_* environment variables for consistency
        with other persistence components.

        Returns:
            Configured Redis client

        Raises:
            ValueError: If required Redis config is missing
        """
        from sk_agents.configs import (
            TA_REDIS_DB,
            TA_REDIS_HOST,
            TA_REDIS_PORT,
            TA_REDIS_PWD,
            TA_REDIS_SSL,
        )

        host = self.app_config.get(TA_REDIS_HOST.env_name)
        port_str = self.app_config.get(TA_REDIS_PORT.env_name)
        db_str = self.app_config.get(TA_REDIS_DB.env_name, default="0")
        ssl_str = self.app_config.get(TA_REDIS_SSL.env_name, default="false")
        pwd = self.app_config.get(TA_REDIS_PWD.env_name, default=None)

        if not host:
            raise ValueError("TA_REDIS_HOST must be configured for Redis discovery manager")
        if not port_str:
            raise ValueError("TA_REDIS_PORT must be configured for Redis discovery manager")

        port = int(port_str)
        db = int(db_str)
        ssl = strtobool(ssl_str)

        logger.info(
            f"Creating Redis discovery client: host={host}, port={port}, db={db}, ssl={ssl}"
        )

        return Redis(host=host, port=port, db=db, ssl=ssl, password=pwd)

    def _make_key(self, user_id: str, session_id: str) -> str:
        """
        Create Redis key for storage.

        Format: mcp_state:{user_id}:{session_id}

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            Redis key string
        """
        return f"{self.key_prefix}:{user_id}:{session_id}"

    async def create_discovery(self, state: McpState) -> None:
        """
        Create initial MCP state in Redis.

        Args:
            state: MCP state to create

        Raises:
            DiscoveryCreateError: If state already exists
        """
        key = self._make_key(state.user_id, state.session_id)
        exists = await self.redis.exists(key)
        if exists:
            raise DiscoveryCreateError(
                f"MCP state already exists for user={state.user_id}, session={state.session_id}"
            )

        data = self._serialize(state)
        # Set with TTL
        await self.redis.set(key, data, ex=self.ttl)
        logger.debug(
            f"Created Redis MCP state: user={state.user_id}, session={state.session_id}, "
            f"TTL={self.ttl}s"
        )

    async def load_discovery(self, user_id: str, session_id: str) -> McpState | None:
        """
        Load MCP state from Redis.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            MCP state if exists, None otherwise
        """
        key = self._make_key(user_id, session_id)
        data = await self.redis.get(key)
        if not data:
            return None
        return self._deserialize(data, user_id, session_id)

    async def update_discovery(self, state: McpState) -> None:
        """
        Update existing MCP state in Redis.

        Args:
            state: Updated MCP state

        Raises:
            DiscoveryUpdateError: If state does not exist
        """
        key = self._make_key(state.user_id, state.session_id)
        # Check existence before updating
        exists = await self.redis.exists(key)
        if not exists:
            raise DiscoveryUpdateError(
                f"MCP state not found for user={state.user_id}, session={state.session_id}"
            )

        data = self._serialize(state)
        # Update with TTL to extend expiration
        await self.redis.set(key, data, ex=self.ttl)
        logger.debug(f"Updated Redis MCP state: user={state.user_id}, session={state.session_id}")

    async def delete_discovery(self, user_id: str, session_id: str) -> None:
        """
        Delete discovery state from Redis.

        Args:
            user_id: User ID
            session_id: Session ID
        """
        key = self._make_key(user_id, session_id)
        await self.redis.delete(key)
        logger.debug(f"Deleted Redis discovery state: user={user_id}, session={session_id}")

    async def mark_completed(self, user_id: str, session_id: str) -> None:
        """
        Mark discovery as completed in Redis using atomic operation.

        If state doesn't exist, auto-creates it with discovery_completed=True
        and empty discovered_servers dict. A warning is logged when auto-creating.

        Uses Lua script for atomic read-modify-write to prevent race conditions
        in multi-worker deployments.

        Args:
            user_id: User ID
            session_id: Session ID
        """
        key = self._make_key(user_id, session_id)

        # Lua script for atomic mark_completed operation
        lua_script = """
        local key = KEYS[1]
        local ttl = tonumber(ARGV[1])
        local data = redis.call('GET', key)

        if data then
            -- State exists, update discovery_completed field
            local obj = cjson.decode(data)
            obj.discovery_completed = true
            local updated_data = cjson.encode(obj)
            redis.call('SET', key, updated_data, 'EX', ttl)
            return 1
        else
            -- State doesn't exist, return 0 to signal auto-create
            return 0
        end
        """

        result = await self.redis.eval(lua_script, 1, key, self.ttl)

        if result == 1:
            logger.debug(f"Marked discovery completed: user={user_id}, session={session_id}")
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
            data = self._serialize(state)
            await self.redis.set(key, data, ex=self.ttl)
            logger.debug(f"Auto-created discovery state: user={user_id}, session={session_id}")

    async def is_completed(self, user_id: str, session_id: str) -> bool:
        """
        Check if discovery is completed in Redis.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            True if discovery completed, False otherwise
        """
        state = await self.load_discovery(user_id, session_id)
        return state.discovery_completed if state else False

    async def store_mcp_session(
        self, user_id: str, session_id: str, server_name: str, mcp_session_id: str
    ) -> None:
        """
        Store MCP session ID for a server using atomic Lua script.

        Args:
            user_id: User ID
            session_id: Teal agent session ID
            server_name: Name of the MCP server
            mcp_session_id: MCP session ID from server
        """
        key = self._make_key(user_id, session_id)

        # Lua script for atomic store operation
        lua_script = """
        local key = KEYS[1]
        local ttl = tonumber(ARGV[1])
        local server_name = ARGV[2]
        local mcp_session_id = ARGV[3]
        local timestamp = ARGV[4]

        local data = redis.call('GET', key)
        local obj

        if data then
            -- State exists, update it
            obj = cjson.decode(data)
        else
            -- State doesn't exist, create minimal state
            obj = {
                user_id = ARGV[5],
                session_id = ARGV[6],
                discovered_servers = {},
                discovery_completed = false,
                created_at = timestamp
            }
        end

        -- Ensure server entry exists
        if not obj.discovered_servers[server_name] then
            obj.discovered_servers[server_name] = {}
        end

        -- Store session data
        if not obj.discovered_servers[server_name].session then
            obj.discovered_servers[server_name].session = {}
        end

        obj.discovered_servers[server_name].session.mcp_session_id = mcp_session_id
        local sess = obj.discovered_servers[server_name].session
        sess.created_at = sess.created_at or timestamp
        sess.last_used_at = timestamp

        local updated_data = cjson.encode(obj)
        redis.call('SET', key, updated_data, 'EX', ttl)
        return 1
        """

        timestamp = datetime.now(UTC).isoformat()
        await self.redis.eval(
            lua_script,
            1,
            key,
            self.ttl,
            server_name,
            mcp_session_id,
            timestamp,
            user_id,
            session_id,
        )

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
        state = await self.load_discovery(user_id, session_id)

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
        Update last_used timestamp using atomic Lua script.

        Args:
            user_id: User ID
            session_id: Teal agent session ID
            server_name: Name of the MCP server

        Raises:
            DiscoveryUpdateError: If state or server doesn't exist
        """
        key = self._make_key(user_id, session_id)

        # Lua script for atomic update
        lua_script = """
        local key = KEYS[1]
        local ttl = tonumber(ARGV[1])
        local server_name = ARGV[2]
        local timestamp = ARGV[3]

        local data = redis.call('GET', key)
        if not data then
            return 0  -- State not found
        end

        local obj = cjson.decode(data)

        if not obj.discovered_servers[server_name] then
            return -1  -- Server not found
        end

        if not obj.discovered_servers[server_name].session then
            obj.discovered_servers[server_name].session = {}
        end
        obj.discovered_servers[server_name].session.last_used_at = timestamp

        local updated_data = cjson.encode(obj)
        redis.call('SET', key, updated_data, 'EX', ttl)
        return 1
        """

        timestamp = datetime.now(UTC).isoformat()
        result = await self.redis.eval(lua_script, 1, key, self.ttl, server_name, timestamp)

        if result == 0:
            raise DiscoveryUpdateError(
                f"MCP state not found for user={user_id}, session={session_id}"
            )
        elif result == -1:
            raise DiscoveryUpdateError(
                f"Server {server_name} not found in state for user={user_id}, session={session_id}"
            )

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
        key = self._make_key(user_id, session_id)

        lua_script = """
        local key = KEYS[1]
        local server_name = ARGV[1]
        local ttl = tonumber(ARGV[2])
        local expected_session_id = ARGV[3]

        local data = redis.call('GET', key)
        if not data then
            return 0 -- state missing
        end

        local obj = cjson.decode(data)
        if not obj.discovered_servers[server_name] then
            return -1 -- server missing
        end

        -- Only clear if expected matches or no expectation provided
        if obj.discovered_servers[server_name].session then
            local current = obj.discovered_servers[server_name].session.mcp_session_id
            if expected_session_id ~= nil and expected_session_id ~= '' then
                if current ~= expected_session_id then
                    return -2  -- session changed, skip clear
                end
            end
        end

        obj.discovered_servers[server_name].session = nil

        local updated_data = cjson.encode(obj)
        redis.call('SET', key, updated_data, 'EX', ttl)
        return 1
        """

        expected_arg = expected_session_id or ""
        result = await self.redis.eval(lua_script, 1, key, server_name, self.ttl, expected_arg)
        if result == 0:
            logger.debug(
                f"clear_mcp_session: state missing for user={user_id}, session={session_id}"
            )
        elif result == -1:
            logger.debug(
                f"clear_mcp_session: server missing for user={user_id}, "
                f"session={session_id}, server={server_name}"
            )
        elif result == -2:
            logger.debug(
                f"clear_mcp_session: session changed for user={user_id}, "
                f"session={session_id}, server={server_name}"
            )
        else:
            logger.debug(
                f"Cleared MCP session for server={server_name}, "
                f"user={user_id}, session={session_id}"
            )

    def _serialize(self, state: McpState) -> str:
        """
        Serialize MCP state to JSON.

        Args:
            state: MCP state to serialize

        Returns:
            JSON string representation
        """
        return json.dumps(
            {
                "user_id": state.user_id,
                "session_id": state.session_id,
                "discovered_servers": state.discovered_servers,
                "discovery_completed": state.discovery_completed,
                "created_at": state.created_at.isoformat(),
                "failed_servers": state.failed_servers,
            }
        )

    def _deserialize(self, data: str | bytes, user_id: str, session_id: str) -> McpState:
        """
        Deserialize JSON to MCP state object.

        Args:
            data: JSON string or bytes from Redis
            user_id: User ID (for validation)
            session_id: Session ID (for validation)

        Returns:
            McpState object

        Raises:
            ValueError: If deserialized user_id/session_id don't match parameters
        """
        # Handle bytes from Redis
        if isinstance(data, bytes):
            data = data.decode("utf-8")

        obj = json.loads(data)

        # Validate that serialized data matches the key parameters
        if obj["user_id"] != user_id:
            raise ValueError(
                f"Deserialized user_id '{obj['user_id']}' does not match "
                f"expected user_id '{user_id}'"
            )
        if obj["session_id"] != session_id:
            raise ValueError(
                f"Deserialized session_id '{obj['session_id']}' does not match "
                f"expected session_id '{session_id}'"
            )

        return McpState(
            user_id=user_id,
            session_id=session_id,
            discovered_servers=obj["discovered_servers"],
            discovery_completed=obj["discovery_completed"],
            created_at=datetime.fromisoformat(obj["created_at"]),
            failed_servers=obj.get("failed_servers", {}),
        )
