"""
Redis MCP Discovery Manager

Provides Redis-backed implementation for production deployments.
Follows the same pattern as Redis persistence and auth storage.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from redis.asyncio import Redis
from ska_utils import AppConfig, strtobool

from sk_agents.mcp_discovery.mcp_discovery_manager import (
    DiscoveryCreateError,
    DiscoveryUpdateError,
    McpDiscoveryManager,
    McpDiscoveryState,
)

logger = logging.getLogger(__name__)


class RedisDiscoveryManager(McpDiscoveryManager):
    """
    Redis-backed implementation of MCP discovery manager.

    Stores discovery state in Redis for:
    - Production deployments
    - Multi-instance horizontal scaling
    - Persistence across server restarts
    - Shared state across distributed systems

    Uses the same Redis configuration as other components (TA_REDIS_*).
    """

    def __init__(self, app_config: AppConfig, redis_client: Optional[Redis] = None):
        """
        Initialize Redis discovery manager.

        Args:
            app_config: Application configuration for Redis connection
            redis_client: Optional pre-configured Redis client (for testing)
        """
        self.app_config = app_config
        self.redis = redis_client or self._create_redis_client()
        self.key_prefix = "mcp_discovery"

        # TTL support: Default to 24 hours (86400 seconds)
        from sk_agents.configs import TA_REDIS_TTL
        ttl_str = self.app_config.get(TA_REDIS_TTL.env_name)
        if ttl_str:
            self.ttl = int(ttl_str)
        else:
            # Default to 24 hours for discovery state
            self.ttl = 86400

        logger.debug(f"Redis discovery manager initialized with TTL={self.ttl}s")

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self.redis:
            await self.redis.close()
            logger.debug("Redis discovery manager connection closed")

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

        Format: mcp_discovery:{user_id}:{session_id}

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            Redis key string
        """
        return f"{self.key_prefix}:{user_id}:{session_id}"

    async def create_discovery(self, state: McpDiscoveryState) -> None:
        """
        Create initial discovery state in Redis.

        Args:
            state: Discovery state to create

        Raises:
            DiscoveryCreateError: If state already exists
        """
        key = self._make_key(state.user_id, state.session_id)
        exists = await self.redis.exists(key)
        if exists:
            raise DiscoveryCreateError(
                f"Discovery state already exists for user={state.user_id}, "
                f"session={state.session_id}"
            )

        data = self._serialize(state)
        # Set with TTL
        await self.redis.set(key, data, ex=self.ttl)
        logger.debug(
            f"Created Redis discovery state: user={state.user_id}, session={state.session_id}, "
            f"TTL={self.ttl}s"
        )

    async def load_discovery(
        self, user_id: str, session_id: str
    ) -> Optional[McpDiscoveryState]:
        """
        Load discovery state from Redis.

        Args:
            user_id: User ID
            session_id: Session ID

        Returns:
            Discovery state if exists, None otherwise
        """
        key = self._make_key(user_id, session_id)
        data = await self.redis.get(key)
        if not data:
            return None
        return self._deserialize(data, user_id, session_id)

    async def update_discovery(self, state: McpDiscoveryState) -> None:
        """
        Update existing discovery state in Redis.

        Args:
            state: Updated discovery state

        Raises:
            DiscoveryUpdateError: If state does not exist
        """
        key = self._make_key(state.user_id, state.session_id)
        # Check existence before updating
        exists = await self.redis.exists(key)
        if not exists:
            raise DiscoveryUpdateError(
                f"Discovery state not found for user={state.user_id}, "
                f"session={state.session_id}"
            )

        data = self._serialize(state)
        # Update with TTL to extend expiration
        await self.redis.set(key, data, ex=self.ttl)
        logger.debug(
            f"Updated Redis discovery state: user={state.user_id}, session={state.session_id}"
        )

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
            logger.debug(
                f"Marked discovery completed: user={user_id}, session={session_id}"
            )
        else:
            # Auto-create state if it doesn't exist
            logger.warning(
                f"Discovery state not found for user={user_id}, session={session_id}. "
                f"Auto-creating with discovery_completed=True."
            )
            state = McpDiscoveryState(
                user_id=user_id,
                session_id=session_id,
                discovered_servers={},
                discovery_completed=True,
                created_at=datetime.now(timezone.utc),
            )
            data = self._serialize(state)
            await self.redis.set(key, data, ex=self.ttl)
            logger.debug(
                f"Auto-created discovery state: user={user_id}, session={session_id}"
            )

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

    def _serialize(self, state: McpDiscoveryState) -> str:
        """
        Serialize discovery state to JSON.

        Args:
            state: Discovery state to serialize

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
            }
        )

    def _deserialize(
        self, data: str | bytes, user_id: str, session_id: str
    ) -> McpDiscoveryState:
        """
        Deserialize JSON to discovery state object.

        Args:
            data: JSON string or bytes from Redis
            user_id: User ID (for validation)
            session_id: Session ID (for validation)

        Returns:
            McpDiscoveryState object

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

        return McpDiscoveryState(
            user_id=user_id,
            session_id=session_id,
            discovered_servers=obj["discovered_servers"],
            discovery_completed=obj["discovery_completed"],
            created_at=datetime.fromisoformat(obj["created_at"]),
        )
