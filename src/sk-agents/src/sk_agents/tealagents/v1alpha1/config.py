from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from sk_agents.plugin_catalog.models import GovernanceOverride


class McpServerConfig(BaseModel):
    """Configuration for an MCP server connection supporting multiple transports."""
    model_config = ConfigDict(extra="allow")
    
    name: str
    # Supported transports: stdio for local servers, http for remote servers
    transport: Literal["stdio", "http"] = "stdio"
    
    # Stdio transport fields
    command: Optional[str] = None
    args: List[str] = []
    env: Optional[Dict[str, str]] = None
    
    # HTTP transport fields
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None  # Non-sensitive headers only
    timeout: Optional[float] = None  # Will be set automatically if not provided
    sse_read_timeout: Optional[float] = None  # Will be set automatically if not provided
    verify_ssl: bool = True  # Allow opt-out for dev; defaults to verified SSL

    # Server-level authentication for tool catalog integration
    auth_server: Optional[str] = None  # OAuth2 authorization server URL
    scopes: List[str] = []  # Required OAuth2 scopes for this server's tools

    # Tool-specific governance overrides (optional)
    tool_governance_overrides: Optional[Dict[str, GovernanceOverride]] = None

    # Server trust level for additional governance controls
    trust_level: Literal["trusted", "sandboxed", "untrusted"] = "untrusted"

    # Request-level timeout for individual MCP operations (seconds)
    request_timeout: Optional[float] = 30.0

    # Optional per-server user header injection (opt-in)
    user_id_header: Optional[str] = None          # e.g., "Arcade-User-Id"
    user_id_source: Optional[Literal["auth", "env"]] = None  # where to read the value
    user_id_env_var: Optional[str] = None         # env var name when source == "env"

    # OAuth 2.1 Configuration (MCP Compliance)
    oauth_client_id: Optional[str] = None  # Pre-registered OAuth client ID
    oauth_client_secret: Optional[str] = None  # Client secret (confidential clients only)
    canonical_uri: Optional[str] = None  # Explicit canonical URI override
    enable_dynamic_registration: bool = True  # Try RFC7591 dynamic registration

    # MCP Protocol Version (for conditional OAuth parameter inclusion)
    protocol_version: Optional[str] = None  # MCP protocol version (e.g., "2025-06-18")

    # Server Metadata Discovery Configuration (RFC 8414/9728)
    enable_metadata_discovery: bool = True  # Enable RFC 8414/9728 discovery
    metadata_cache_ttl: int = 3600  # Metadata cache TTL in seconds (default: 1 hour)

    @property
    def effective_canonical_uri(self) -> str:
        """
        Get canonical MCP server URI for resource parameter binding.

        Per MCP spec, canonical URI must be:
        - Absolute HTTPS URI
        - Lowercase scheme and host
        - Optional port and path

        Returns:
            str: Canonical URI (either explicit or computed from url)

        Raises:
            ValueError: If cannot determine canonical URI
        """
        from sk_agents.mcp_client import normalize_canonical_uri

        # Use explicit canonical_uri if provided
        if self.canonical_uri:
            return normalize_canonical_uri(self.canonical_uri)

        # Compute from url for HTTP transport
        if self.transport == "http" and self.url:
            return normalize_canonical_uri(self.url)

        # Stdio transport doesn't need canonical URI (no OAuth)
        if self.transport == "stdio":
            raise ValueError(
                f"Canonical URI not applicable for stdio transport (server: {self.name})"
            )

        raise ValueError(
            f"Cannot determine canonical URI for server '{self.name}'. "
            f"Provide 'canonical_uri' or ensure 'url' is set for HTTP transport."
        )

    @property
    def oauth_redirect_uri(self) -> str:
        """Get platform OAuth redirect URI from config."""
        from ska_utils import AppConfig
        from sk_agents.configs import TA_OAUTH_REDIRECT_URI

        app_config = AppConfig()
        return app_config.get(TA_OAUTH_REDIRECT_URI.env_name)
    
    @model_validator(mode='after')
    def validate_transport_fields(self):
        """Validate that required fields are provided for the selected transport."""
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("'command' is required for stdio transport")
            # Basic security validation
            if any(char in (self.command or "") for char in [';', '&', '|', '`', '$']):
                raise ValueError("Command contains potentially unsafe characters")
        elif self.transport == "http":
            if not self.url:
                raise ValueError("'url' is required for http transport")
            # Validate URL format
            if not (self.url.startswith('http://') or self.url.startswith('https://')):
                raise ValueError("HTTP transport URL must start with 'http://' or 'https://'")

            # Set smart defaults for timeouts if not provided
            if self.timeout is None:
                self.timeout = 30.0  # Default timeout
            if self.sse_read_timeout is None:
                self.sse_read_timeout = 300.0  # Default SSE read timeout

            # Warn if no authentication configured for HTTP server
            has_oauth = self.auth_server and self.scopes
            has_auth_header = (
                self.headers
                and any(k.lower() == "authorization" for k in self.headers.keys())
            )

            if not has_oauth and not has_auth_header:
                import warnings
                warnings.warn(
                    f"MCP server '{self.name}' is configured without authentication. "
                    f"This should only be used for:\n"
                    f"  - Public/read-only MCP servers\n"
                    f"  - Development/testing environments\n"
                    f"  - Internal networks with network-level security\n"
                    f"For production use with sensitive data, configure OAuth "
                    f"(auth_server + scopes) or provide Authorization header.",
                    UserWarning,
                    stacklevel=2
                )

            # OAuth validation - only if using OAuth
            # If one OAuth field is provided, both must be provided
            if self.auth_server or self.scopes:
                if not (self.auth_server and self.scopes):
                    raise ValueError(
                        "Both auth_server and scopes are required when using OAuth authentication. "
                        "Provide both or neither for simple header-based authentication."
                    )

        # OAuth-specific validation (only when OAuth is configured)
        if self.auth_server and self.scopes:
            # Validate auth_server URL format
            if not self.auth_server.startswith(('http://', 'https://')):
                raise ValueError("auth_server must be a valid HTTP/HTTPS URL")

            # HTTPS enforcement (per OAuth 2.1 and MCP spec)
            from ska_utils import AppConfig
            from sk_agents.configs import TA_MCP_OAUTH_STRICT_HTTPS_VALIDATION
            from sk_agents.mcp_client import validate_https_url

            app_config = AppConfig()
            strict_https = app_config.get(TA_MCP_OAUTH_STRICT_HTTPS_VALIDATION.env_name).lower() == "true"

            if strict_https:
                # Validate auth_server uses HTTPS (or localhost)
                if not validate_https_url(self.auth_server, allow_localhost=True):
                    raise ValueError(
                        f"auth_server must use HTTPS (or http://localhost for development): {self.auth_server}. "
                        f"Disable with TA_MCP_OAUTH_STRICT_HTTPS_VALIDATION=false"
                    )

                # Validate redirect_uri uses HTTPS (or localhost)
                redirect_uri = self.oauth_redirect_uri
                if redirect_uri and not validate_https_url(redirect_uri, allow_localhost=True):
                    raise ValueError(
                        f"OAuth redirect_uri must use HTTPS (or http://localhost for development): {redirect_uri}. "
                        f"Disable with TA_MCP_OAUTH_STRICT_HTTPS_VALIDATION=false"
                    )

        return self


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    model: str
    system_prompt: str
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    max_tokens: int | None = None
    reasoning_effort: str | None = None
    plugins: list[str] | None = None
    remote_plugins: list[str] | None = None
    mcp_servers: list[McpServerConfig] | None = None
