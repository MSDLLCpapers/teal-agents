"""
OAuth Error Handler

Handles OAuth error responses and WWW-Authenticate header parsing per:
- RFC 6750: Bearer Token Usage
- RFC 9728: Protected Resource Metadata
- MCP Specification 2025-06-18

Key functionality:
- Parse WWW-Authenticate headers from 401 responses
- Extract error codes: invalid_token, insufficient_scope, etc.
- Extract scope requirements for re-authorization
- Extract resource_metadata URL for RFC 9728 discovery
"""

import logging
import re

logger = logging.getLogger(__name__)


class WWWAuthenticateChallenge:
    """
    Parsed WWW-Authenticate challenge from 401 response.

    Per RFC 6750 Section 3:
    WWW-Authenticate: Bearer realm="example",
                      error="invalid_token",
                      error_description="The access token expired",
                      scope="read write",
                      resource_metadata="https://api.example.com/.well-known/oauth-protected-resource"
    """

    def __init__(
        self,
        realm: str | None = None,
        error: str | None = None,
        error_description: str | None = None,
        error_uri: str | None = None,
        scope: str | None = None,
        resource_metadata: str | None = None,
    ):
        self.realm = realm
        self.error = error
        self.error_description = error_description
        self.error_uri = error_uri
        self.scope = scope  # Space-separated scope string
        self.resource_metadata = resource_metadata

    @property
    def scopes(self) -> list[str]:
        """Get scopes as list."""
        return self.scope.split() if self.scope else []

    def requires_reauth(self) -> bool:
        """Check if error requires re-authorization."""
        return self.error in ("invalid_token", "insufficient_scope")

    def is_token_expired(self) -> bool:
        """Check if error indicates token expiry."""
        return self.error == "invalid_token"

    def is_insufficient_scope(self) -> bool:
        """Check if error indicates insufficient scopes."""
        return self.error == "insufficient_scope"

    def __repr__(self) -> str:
        return (
            f"WWWAuthenticateChallenge(error={self.error}, scope={self.scope}, realm={self.realm})"
        )


def parse_www_authenticate_header(header_value: str) -> WWWAuthenticateChallenge | None:
    """
    Parse WWW-Authenticate header per RFC 6750 + RFC 9728.

    Format:
        WWW-Authenticate: Bearer realm="example",
                          error="invalid_token",
                          error_description="The access token expired",
                          scope="read write",
                          resource_metadata="https://..."

    Args:
        header_value: Value of WWW-Authenticate header

    Returns:
        WWWAuthenticateChallenge: Parsed challenge, or None if not a Bearer challenge

    Raises:
        ValueError: If header is malformed
    """
    if not header_value:
        return None

    # Check if it's a Bearer challenge
    if not header_value.strip().lower().startswith("bearer"):
        logger.debug(f"WWW-Authenticate header is not Bearer type: {header_value}")
        return None

    # Remove "Bearer " prefix
    params_str = header_value[6:].strip()

    # Parse parameters using regex
    # Matches: param="value" or param=value (unquoted)
    pattern = r'(\w+)=(?:"([^"]*)"|([^\s,]+))'
    matches = re.findall(pattern, params_str)

    params: dict[str, str] = {}
    for match in matches:
        param_name = match[0]
        # Use quoted value if present, otherwise unquoted
        param_value = match[1] if match[1] else match[2]
        params[param_name] = param_value

    # Build challenge object
    challenge = WWWAuthenticateChallenge(
        realm=params.get("realm"),
        error=params.get("error"),
        error_description=params.get("error_description"),
        error_uri=params.get("error_uri"),
        scope=params.get("scope"),
        resource_metadata=params.get("resource_metadata"),
    )

    logger.debug(f"Parsed WWW-Authenticate challenge: {challenge}")
    return challenge


def extract_field_from_www_authenticate(header_value: str, field_name: str) -> str | None:
    """
    Extract a specific field from WWW-Authenticate header.

    Convenience function for extracting single fields.

    Args:
        header_value: Value of WWW-Authenticate header
        field_name: Field to extract (e.g., "error", "scope", "resource_metadata")

    Returns:
        Field value, or None if not present
    """
    challenge = parse_www_authenticate_header(header_value)
    if not challenge:
        return None

    return getattr(challenge, field_name, None)


class OAuthErrorHandler:
    """
    Handler for OAuth error responses.

    Provides structured error handling for:
    - 401 Unauthorized (invalid_token, insufficient_scope)
    - 403 Forbidden (insufficient permissions)
    - 400 Bad Request (malformed request)
    """

    @staticmethod
    def handle_401_response(response_headers: dict[str, str]) -> WWWAuthenticateChallenge | None:
        """
        Handle 401 Unauthorized response.

        Extracts WWW-Authenticate challenge for further processing.

        Args:
            response_headers: HTTP response headers

        Returns:
            Parsed WWW-Authenticate challenge, or None if header missing
        """
        www_auth = response_headers.get("WWW-Authenticate") or response_headers.get(
            "www-authenticate"
        )
        if not www_auth:
            logger.warning("401 response missing WWW-Authenticate header")
            return None

        return parse_www_authenticate_header(www_auth)

    @staticmethod
    def should_refresh_token(challenge: WWWAuthenticateChallenge | None) -> bool:
        """
        Determine if token should be refreshed based on error.

        Args:
            challenge: Parsed WWW-Authenticate challenge

        Returns:
            True if token refresh should be attempted
        """
        if not challenge:
            return False

        # Refresh on invalid_token error
        return challenge.is_token_expired()

    @staticmethod
    def should_reauthorize(challenge: WWWAuthenticateChallenge | None) -> bool:
        """
        Determine if re-authorization is required.

        Args:
            challenge: Parsed WWW-Authenticate challenge

        Returns:
            True if re-authorization flow should be initiated
        """
        if not challenge:
            return False

        # Re-authorize on insufficient_scope or other auth errors
        return challenge.is_insufficient_scope() or (
            challenge.error and challenge.error not in ("invalid_token",)
        )

    @staticmethod
    def get_required_scopes(challenge: WWWAuthenticateChallenge | None) -> list[str]:
        """
        Extract required scopes from challenge.

        For insufficient_scope errors, this returns the scopes needed.

        Args:
            challenge: Parsed WWW-Authenticate challenge

        Returns:
            List of required scopes, empty if none specified
        """
        if not challenge:
            return []

        return challenge.scopes


def build_www_authenticate_header(
    error: str,
    error_description: str | None = None,
    scope: str | None = None,
    realm: str | None = None,
    resource_metadata: str | None = None,
) -> str:
    """
    Build WWW-Authenticate header per RFC 6750 + RFC 9728.

    For use when implementing MCP servers that need to challenge clients.

    Args:
        error: OAuth error code (e.g., "invalid_token", "insufficient_scope")
        error_description: Human-readable error description
        scope: Required scope(s) (space-separated)
        realm: Protection realm
        resource_metadata: URL for Protected Resource Metadata (RFC 9728)

    Returns:
        str: Formatted WWW-Authenticate header value

    Example:
        >>> build_www_authenticate_header(
        ...     error="insufficient_scope",
        ...     error_description="Token lacks required scopes",
        ...     scope="read write",
        ...     resource_metadata="https://api.example.com/.well-known/oauth-protected-resource"
        ... )  # doctest: +SKIP
        'Bearer error="insufficient_scope", ...'
    """
    parts = ["Bearer"]

    if realm:
        parts.append(f'realm="{realm}"')

    parts.append(f'error="{error}"')

    if error_description:
        parts.append(f'error_description="{error_description}"')

    if scope:
        parts.append(f'scope="{scope}"')

    if resource_metadata:
        parts.append(f'resource_metadata="{resource_metadata}"')

    return ", ".join(parts)
