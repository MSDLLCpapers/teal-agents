"""
MCP OAuth 2.1 Authentication Components

This module provides OAuth 2.1 compliant authentication for MCP (Model Context Protocol) servers.
All components follow the MCP specification (2025-06-18) for authorization:
https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization

Key Features:
- PKCE (Proof Key for Code Exchange) for authorization code flow
- Resource parameter binding for token audience validation
- State parameter for CSRF protection
- Token refresh with rotation
- Server metadata discovery (RFC8414, RFC9728)
- Dynamic client registration (RFC7591)

Architecture:
- This module is isolated from platform authentication (RequestAuthorizer)
- Platform auth: Validates user to platform, returns user_id
- Service auth (MCP): Manages OAuth tokens for external services per user

Components:
- oauth_client: Main OAuth 2.1 client for authorization flows
- oauth_pkce: PKCE generation and validation
- oauth_models: Request/response models for OAuth flows
- oauth_state_manager: State and PKCE verifier storage for OAuth flows
- server_metadata: Authorization server metadata discovery (RFC8414, RFC9728)
- client_registration: Dynamic client registration (RFC7591)
"""

__all__ = [
    "OAuthClient",
    "PKCEManager",
    "OAuthStateManager",
    "AuthorizationRequest",
    "TokenRequest",
    "TokenResponse",
]

# Lazy imports to avoid circular dependencies
def __getattr__(name: str):
    if name == "OAuthClient":
        from sk_agents.auth.oauth_client import OAuthClient
        return OAuthClient
    elif name == "PKCEManager":
        from sk_agents.auth.oauth_pkce import PKCEManager
        return PKCEManager
    elif name == "OAuthStateManager":
        from sk_agents.auth.oauth_state_manager import OAuthStateManager
        return OAuthStateManager
    elif name in ("AuthorizationRequest", "TokenRequest", "TokenResponse"):
        from sk_agents.auth import oauth_models
        return getattr(oauth_models, name)

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
