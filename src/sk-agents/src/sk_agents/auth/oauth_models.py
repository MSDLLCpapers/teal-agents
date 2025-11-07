"""
OAuth 2.1 Request and Response Models

Models for OAuth authorization flows following MCP specification.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


class AuthorizationRequest(BaseModel):
    """
    OAuth 2.1 Authorization Request

    Used to construct authorization URL with all required parameters.
    Follows MCP spec requirement for PKCE and resource parameter.

    Note: resource parameter is optional and should only be included if:
    - MCP protocol version >= 2025-06-18, OR
    - Protected Resource Metadata has been discovered
    """

    auth_server: HttpUrl = Field(..., description="Authorization server base URL")
    authorization_endpoint: HttpUrl | None = Field(None, description="Discovered authorization endpoint (RFC 8414)")
    client_id: str = Field(..., description="OAuth client ID")
    redirect_uri: HttpUrl = Field(..., description="OAuth callback URL")
    resource: str | None = Field(None, description="Canonical MCP server URI (resource binding) - conditional per protocol version")
    scopes: list[str] = Field(..., description="Requested OAuth scopes")
    state: str = Field(..., description="CSRF protection state parameter")
    code_challenge: str = Field(..., description="PKCE code challenge (S256)")
    code_challenge_method: Literal["S256"] = Field(
        default="S256", description="PKCE challenge method (must be S256)"
    )
    response_type: Literal["code"] = Field(
        default="code", description="OAuth response type (authorization code flow)"
    )


class TokenRequest(BaseModel):
    """
    OAuth 2.1 Token Request

    Used to exchange authorization code for access token.
    Includes PKCE verifier and resource parameter.

    Note: resource parameter is optional and should only be included if:
    - MCP protocol version >= 2025-06-18, OR
    - Protected Resource Metadata has been discovered
    """

    token_endpoint: HttpUrl = Field(..., description="Token endpoint URL")
    grant_type: Literal["authorization_code", "refresh_token"] = Field(
        ..., description="OAuth grant type"
    )
    code: str | None = Field(None, description="Authorization code (for authorization_code grant)")
    refresh_token: str | None = Field(None, description="Refresh token (for refresh_token grant)")
    redirect_uri: HttpUrl | None = Field(None, description="OAuth callback URL (must match)")
    code_verifier: str | None = Field(None, description="PKCE code verifier")
    resource: str | None = Field(None, description="Canonical MCP server URI (resource binding) - conditional per protocol version")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str | None = Field(None, description="OAuth client secret (confidential clients only)")
    requested_scopes: list[str] | None = Field(None, description="Requested scopes for validation (prevents escalation attacks)")


class TokenResponse(BaseModel):
    """
    OAuth 2.1 Token Response

    Token endpoint response with access token and metadata.
    """

    access_token: str = Field(..., description="OAuth access token")
    token_type: str = Field(..., description="Token type (usually 'Bearer')")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    refresh_token: str | None = Field(None, description="Refresh token (optional)")
    scope: str | None = Field(None, description="Granted scopes (space-separated)")
    aud: str | None = Field(None, description="Token audience (for validation)")


class RefreshTokenRequest(BaseModel):
    """
    OAuth 2.1 Refresh Token Request

    Request to refresh an expired access token.

    Note: resource parameter is optional and should only be included if:
    - MCP protocol version >= 2025-06-18, OR
    - Protected Resource Metadata has been discovered
    - Must match the original authorization request resource if included
    """

    token_endpoint: HttpUrl = Field(..., description="Token endpoint URL")
    refresh_token: str = Field(..., description="Refresh token")
    resource: str | None = Field(None, description="Canonical MCP server URI (must match original) - conditional per protocol version")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str | None = Field(None, description="OAuth client secret (confidential clients only)")
    grant_type: Literal["refresh_token"] = Field(
        default="refresh_token", description="OAuth grant type"
    )
    requested_scopes: list[str] | None = Field(None, description="Original requested scopes for validation (prevents escalation)")


class OAuthError(BaseModel):
    """
    OAuth Error Response

    Parsed from WWW-Authenticate header or token endpoint error response.
    """

    error: str = Field(..., description="Error code (e.g., 'invalid_token', 'insufficient_scope')")
    error_description: str | None = Field(None, description="Human-readable error description")
    error_uri: str | None = Field(None, description="URL with error information")
    oauth_server_metadata_url: str | None = Field(
        None, description="Authorization server metadata URL (from WWW-Authenticate)"
    )


class MCP401Response(BaseModel):
    """
    MCP-compliant 401 Unauthorized response.

    Per MCP spec, servers should return WWW-Authenticate header with:
    - error: Error code
    - error_description: Human-readable description
    - scope: Required scopes (for insufficient_scope)
    - resource_metadata: URL for RFC 9728 discovery (optional)
    """

    www_authenticate: str = Field(..., description="WWW-Authenticate header value")
    error_code: int = Field(401, description="HTTP status code")
    error_message: str = Field(
        "Authentication required",
        description="Human-readable error message"
    )


class MCP403Response(BaseModel):
    """MCP-compliant 403 Forbidden response."""

    error_code: int = Field(403, description="HTTP status code")
    error_message: str = Field(
        "Insufficient permissions",
        description="Human-readable error message"
    )
    required_scopes: list[str] | None = Field(
        None,
        description="Scopes required for this operation"
    )
