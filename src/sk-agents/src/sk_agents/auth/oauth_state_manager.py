"""
OAuth State Manager

Manages OAuth flow state for CSRF protection.
Stores state parameter + PKCE verifier temporarily during OAuth flow.

Implementation uses AuthStorage with temporary keys and TTL.
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from ska_utils import AppConfig

from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory

logger = logging.getLogger(__name__)


class OAuthFlowState:
    """
    Represents temporary OAuth flow state.

    Stored during authorization request, retrieved during callback.
    """

    def __init__(
        self,
        state: str,
        verifier: str,
        user_id: str,
        server_name: str,
        resource: str,
        scopes: list[str],
        created_at: datetime,
    ):
        self.state = state
        self.verifier = verifier
        self.user_id = user_id
        self.server_name = server_name
        self.resource = resource
        self.scopes = scopes
        self.created_at = created_at

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for storage"""
        return {
            "state": self.state,
            "verifier": self.verifier,
            "user_id": self.user_id,
            "server_name": self.server_name,
            "resource": self.resource,
            "scopes": self.scopes,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthFlowState":
        """Deserialize from storage dict"""
        return cls(
            state=data["state"],
            verifier=data["verifier"],
            user_id=data["user_id"],
            server_name=data["server_name"],
            resource=data["resource"],
            scopes=data["scopes"],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    def is_expired(self, ttl_seconds: int = 300) -> bool:
        """Check if flow state has expired (default 5 minutes)"""
        expires_at = self.created_at + timedelta(seconds=ttl_seconds)
        return datetime.now(timezone.utc) > expires_at


class OAuthStateManager:
    """
    Manager for OAuth flow state and CSRF protection.

    Uses AuthStorage with temporary keys to store state during OAuth flow.
    """

    # Use a special user_id for temporary OAuth flow state
    TEMP_USER_PREFIX = "oauth_flow_temp"

    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize state manager.

        Args:
            ttl_seconds: Time-to-live for state (default 5 minutes)
        """
        self.ttl_seconds = ttl_seconds
        self.auth_storage_factory = AuthStorageFactory(AppConfig())
        self.auth_storage = self.auth_storage_factory.get_auth_storage_manager()

    @staticmethod
    def generate_state() -> str:
        """
        Generate cryptographically random state parameter.

        Returns:
            str: Random state string (URL-safe, 32 bytes)
        """
        return secrets.token_urlsafe(32)

    def store_flow_state(
        self,
        state: str,
        verifier: str,
        user_id: str,
        server_name: str,
        resource: str,
        scopes: list[str],
    ) -> None:
        """
        Store OAuth flow state temporarily.

        Args:
            state: CSRF state parameter
            verifier: PKCE code verifier
            user_id: User ID for this flow
            server_name: MCP server name
            resource: Canonical server URI
            scopes: Requested scopes
        """
        flow_state = OAuthFlowState(
            state=state,
            verifier=verifier,
            user_id=user_id,
            server_name=server_name,
            resource=resource,
            scopes=scopes,
            created_at=datetime.now(timezone.utc),
        )

        # Store with temporary key
        temp_key = f"oauth_state:{state}"

        # Note: Current AuthStorage doesn't support TTL natively
        # We'll implement expiry check on retrieval
        # For production, consider Redis or other storage with native TTL
        try:
            # Use a synthetic user_id for temporary storage
            temp_user = f"{self.TEMP_USER_PREFIX}:{user_id}"
            self.auth_storage.store(temp_user, temp_key, flow_state.to_dict())
            logger.debug(f"Stored OAuth flow state for state={state}, user={user_id}")
        except Exception as e:
            logger.error(f"Failed to store OAuth flow state: {e}")
            raise

    def retrieve_flow_state(self, state: str, user_id: str) -> OAuthFlowState:
        """
        Retrieve and validate OAuth flow state.

        Args:
            state: CSRF state parameter from callback
            user_id: User ID to validate against

        Returns:
            OAuthFlowState: Retrieved flow state

        Raises:
            ValueError: If state not found, expired, or user_id mismatch
        """
        temp_key = f"oauth_state:{state}"
        temp_user = f"{self.TEMP_USER_PREFIX}:{user_id}"

        try:
            # Retrieve from storage
            data = self.auth_storage.retrieve(temp_user, temp_key)

            if not data:
                logger.warning(f"OAuth flow state not found for state={state}")
                raise ValueError("Invalid or expired OAuth state")

            # Handle both dict and object storage
            if not isinstance(data, dict):
                # If AuthStorage returns an object, try to convert
                if hasattr(data, 'to_dict'):
                    data = data.to_dict()
                elif hasattr(data, '__dict__'):
                    data = data.__dict__
                else:
                    logger.error(f"Unexpected flow state data type: {type(data)}")
                    raise ValueError("Invalid OAuth flow state data")

            flow_state = OAuthFlowState.from_dict(data)

            # Validate expiry
            if flow_state.is_expired(self.ttl_seconds):
                logger.warning(f"OAuth flow state expired for state={state}")
                # Clean up expired state
                self.delete_flow_state(state, user_id)
                raise ValueError("OAuth state expired")

            # Validate user_id (CSRF protection)
            if flow_state.user_id != user_id:
                logger.error(
                    f"OAuth flow user_id mismatch: expected={flow_state.user_id}, got={user_id}"
                )
                raise ValueError("OAuth state user mismatch (CSRF attempt?)")

            logger.debug(f"Retrieved valid OAuth flow state for state={state}, user={user_id}")
            return flow_state

        except Exception as e:
            logger.error(f"Failed to retrieve OAuth flow state: {e}")
            raise

    def delete_flow_state(self, state: str, user_id: str) -> None:
        """
        Delete OAuth flow state after use or expiry.

        Args:
            state: CSRF state parameter
            user_id: User ID
        """
        temp_key = f"oauth_state:{state}"
        temp_user = f"{self.TEMP_USER_PREFIX}:{user_id}"

        try:
            # Note: Current AuthStorage may not have a delete method
            # For now, we just log. In production, implement proper cleanup.
            logger.debug(f"Deleting OAuth flow state for state={state}, user={user_id}")
            # self.auth_storage.delete(temp_user, temp_key)  # If available
        except Exception as e:
            logger.warning(f"Failed to delete OAuth flow state: {e}")
            # Non-critical error, continue
