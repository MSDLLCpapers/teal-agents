# MCP Client Technical Specification

**Version:** 3.0
**Last Updated:** 2025-01

## 1. Overview

This specification describes the technical architecture and implementation of Model Context Protocol (MCP) client integration for the Teal Agents platform.

### 1.1 Design Principles

- **Session-scoped discovery**: Tools are discovered once per session and stored externally
- **Request-scoped connections**: Connections are created, pooled, and closed within each request
- **Stateless tool wrappers**: `McpTool` and `McpPlugin` store configuration, not connections
- **External state storage**: Discovery state stored in Redis for horizontal scaling
- **Secure-by-default**: Unknown tools require HITL approval

### 1.2 Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Session-level discovery | Avoid repeated discovery overhead; tools rarely change mid-session |
| Request-scoped connection pooling | Balance efficiency (reuse within request) with resource cleanup |
| External state storage | Enable horizontal scaling and persistence across restarts |
| Lazy connection creation | Only connect to servers when tools are actually called |
| MCP session ID persistence | Support stateful MCP servers across requests |

## 2. Architecture

### 2.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Teal Agents MCP Architecture                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         CONFIGURATION LAYER                          │    │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │    │
│  │  │ McpServerConfig │  │GovernanceOverride│  │   AgentConfig       │  │    │
│  │  │ - name          │  │ - requires_hitl  │  │ - mcp_servers[]     │  │    │
│  │  │ - transport     │  │ - cost           │  │ - plugins[]         │  │    │
│  │  │ - url/command   │  │ - data_sensitivity│  │ - system_prompt    │  │    │
│  │  │ - auth_server   │  └─────────────────┘  └─────────────────────┘  │    │
│  │  │ - scopes        │                                                 │    │
│  │  │ - trust_level   │                                                 │    │
│  │  └─────────────────┘                                                 │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         DISCOVERY LAYER                              │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                    McpPluginRegistry                         │    │    │
│  │  │  - discover_and_materialize(servers, user_id, session_id)   │    │    │
│  │  │  - get_tools_for_session(user_id, session_id)               │    │    │
│  │  │  - _register_tool_in_catalog(tool, server_config)           │    │    │
│  │  │  - _serialize_plugin_data(tools, server_name)               │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                              │                                       │    │
│  │                              ▼                                       │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                    McpStateManager                           │    │    │
│  │  │  - create_discovery() / load_discovery()                    │    │    │
│  │  │  - mark_completed() / is_completed()                        │    │    │
│  │  │  - store_mcp_session() / get_mcp_session()                  │    │    │
│  │  │                                                              │    │    │
│  │  │  Implementations:                                            │    │    │
│  │  │  - InMemoryStateManager (dev/test)                          │    │    │
│  │  │  - RedisStateManager (production)                           │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         CONNECTION LAYER                             │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                  McpConnectionManager                        │    │    │
│  │  │  - __aenter__(): Load stored session IDs                    │    │    │
│  │  │  - __aexit__(): Persist session IDs, close connections      │    │    │
│  │  │  - get_or_create_session(server_name): Lazy connection      │    │    │
│  │  │                                                              │    │    │
│  │  │  Lifecycle: Created per-request, used as async context mgr  │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  │                              │                                       │    │
│  │                              ▼                                       │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │              create_mcp_session_with_retry()                 │    │    │
│  │  │  - Transport selection (stdio / http)                       │    │    │
│  │  │  - OAuth token resolution                                   │    │    │
│  │  │  - MCP session initialization                               │    │    │
│  │  │  - Stale session recovery                                   │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                         EXECUTION LAYER                              │    │
│  │  ┌──────────────────────┐      ┌──────────────────────────────┐     │    │
│  │  │       McpTool        │      │         McpPlugin            │     │    │
│  │  │  - tool_name         │      │  - tools: List[McpTool]      │     │    │
│  │  │  - input_schema      │      │  - server_name               │     │    │
│  │  │  - server_config     │      │  - user_id                   │     │    │
│  │  │  - invoke(conn_mgr)  │      │  - connection_manager        │     │    │
│  │  └──────────────────────┘      │  - @kernel_function methods  │     │    │
│  │           │                    └──────────────────────────────┘     │    │
│  │           │                                 │                        │    │
│  │           └─────────────┬───────────────────┘                        │    │
│  │                         ▼                                            │    │
│  │  ┌─────────────────────────────────────────────────────────────┐    │    │
│  │  │                   Semantic Kernel                            │    │    │
│  │  │  - Plugins registered with kernel.add_plugin()              │    │    │
│  │  │  - Tools exposed as @kernel_function                        │    │    │
│  │  │  - LLM invokes tools via function calling                   │    │    │
│  │  └─────────────────────────────────────────────────────────────┘    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            Complete Request Flow                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 1: SESSION DISCOVERY (once per session)                        │    │
│  │                                                                       │    │
│  │  User Request ──▶ Handler.invoke()                                   │    │
│  │       │                                                               │    │
│  │       ▼                                                               │    │
│  │  _ensure_session_discovery(user_id, session_id)                      │    │
│  │       │                                                               │    │
│  │       ├──▶ McpStateManager.is_completed()? ──▶ Skip if true         │    │
│  │       │                                                               │    │
│  │       ▼                                                               │    │
│  │  McpPluginRegistry.discover_and_materialize()                        │    │
│  │       │                                                               │    │
│  │       ├──▶ For each server:                                          │    │
│  │       │      │                                                        │    │
│  │       │      ├──▶ resolve_server_auth_headers()                      │    │
│  │       │      │      └──▶ AuthRequiredError if no token               │    │
│  │       │      │                                                        │    │
│  │       │      ├──▶ create_mcp_session_with_retry()                    │    │
│  │       │      │      ├──▶ stdio_client() or streamablehttp_client()   │    │
│  │       │      │      └──▶ initialize_mcp_session()                    │    │
│  │       │      │                                                        │    │
│  │       │      ├──▶ session.list_tools()                               │    │
│  │       │      │                                                        │    │
│  │       │      ├──▶ _register_tool_in_catalog() (for governance)       │    │
│  │       │      │                                                        │    │
│  │       │      └──▶ _serialize_plugin_data() ──▶ McpStateManager       │    │
│  │       │                                                               │    │
│  │       └──▶ McpStateManager.mark_completed()                          │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                      │                                       │
│                                      ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │ PHASE 2: REQUEST EXECUTION (every request)                           │    │
│  │                                                                       │    │
│  │  McpConnectionManager created (request-scoped)                       │    │
│  │       │                                                               │    │
│  │       ├──▶ __aenter__(): Load stored MCP session IDs                │    │
│  │       │                                                               │    │
│  │       ▼                                                               │    │
│  │  KernelBuilder.load_mcp_plugins()                                    │    │
│  │       │                                                               │    │
│  │       ├──▶ McpPluginRegistry.get_tools_for_session()                │    │
│  │       │                                                               │    │
│  │       ├──▶ Create McpPlugin instances (with connection_manager)      │    │
│  │       │                                                               │    │
│  │       └──▶ kernel.add_plugin() for each server                       │    │
│  │                                                                       │    │
│  │       ▼                                                               │    │
│  │  Agent execution (LLM + tool calls)                                  │    │
│  │       │                                                               │    │
│  │       ├──▶ LLM decides to call MCP tool                              │    │
│  │       │                                                               │    │
│  │       ├──▶ McpPlugin.tool_function() called                          │    │
│  │       │      │                                                        │    │
│  │       │      └──▶ McpTool.invoke(connection_manager)                 │    │
│  │       │             │                                                 │    │
│  │       │             ├──▶ connection_manager.get_or_create_session()  │    │
│  │       │             │      └──▶ Lazy connection (reused if exists)   │    │
│  │       │             │                                                 │    │
│  │       │             └──▶ session.call_tool(tool_name, args)          │    │
│  │       │                                                               │    │
│  │       └──▶ Return result to LLM                                      │    │
│  │                                                                       │    │
│  │       ▼                                                               │    │
│  │  McpConnectionManager.__aexit__()                                    │    │
│  │       │                                                               │    │
│  │       ├──▶ Persist MCP session IDs to McpStateManager               │    │
│  │       │                                                               │    │
│  │       └──▶ Close all connections                                     │    │
│  │                                                                       │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## 3. Core Components

### 3.1 McpServerConfig

**Location:** `tealagents/v1alpha1/config.py`

Configuration model for MCP server connections.

```python
class McpServerConfig(BaseModel):
    # Identity
    name: str                                           # Unique server identifier
    transport: Literal["stdio", "http"] | None = None   # Inferred if omitted

    # Stdio transport
    command: str | None = None                          # Executable command
    args: list[str] = []                                # Command arguments
    env: dict[str, str] | None = None                   # Environment variables

    # HTTP transport
    url: str | None = None                              # MCP endpoint URL
    headers: dict[str, str] | None = None               # Non-sensitive headers
    timeout: float | None = 30.0                        # Connection timeout
    sse_read_timeout: float | None = 300.0              # SSE read timeout
    verify_ssl: bool = True                             # SSL verification

    # OAuth 2.1
    auth_server: str | None = None                      # Authorization server URL
    scopes: list[str] = []                              # Required OAuth scopes
    oauth_client_id: str | None = None                  # Pre-registered client ID
    oauth_client_secret: str | None = None              # Client secret
    canonical_uri: str | None = None                    # Explicit canonical URI
    enable_dynamic_registration: bool = True            # Try RFC 7591
    protocol_version: str | None = None                 # MCP protocol version

    # Governance
    trust_level: Literal["trusted", "sandboxed", "untrusted"] = "untrusted"
    tool_governance_overrides: dict[str, GovernanceOverride] | None = None

    # User context
    user_id_header: str | None = None                   # Header for user ID injection
    user_id_source: Literal["auth", "env"] | None = None

    @property
    def effective_transport(self) -> str:
        """Infer transport from configuration."""
        if self.transport:
            return self.transport
        if self.url and not self.command:
            return "http"
        if self.command and not self.url:
            return "stdio"
        raise ValueError("Cannot infer transport")

    @property
    def effective_canonical_uri(self) -> str:
        """Get canonical URI for OAuth resource binding."""
        return self.canonical_uri or self.url
```

**Validation Rules:**
- `name` is required
- `url` required for HTTP transport
- `command` required for stdio transport
- Warn if HTTP without `auth_server` (security)
- Validate HTTPS for OAuth endpoints

### 3.2 McpStateManager

**Location:** `mcp_discovery/mcp_discovery_manager.py`

Abstract interface for session-scoped state persistence.

```python
class McpState:
    user_id: str                              # User ID for scoping
    session_id: str                           # Session ID for isolation
    discovered_servers: dict[str, dict]       # server_name → {plugin_data, session}
    discovery_completed: bool                 # Discovery completion flag
    failed_servers: dict[str, str]            # Failed servers with error messages
    created_at: datetime                      # State creation timestamp

class McpStateManager(ABC):
    @abstractmethod
    async def create_discovery(self, state: McpState) -> None: ...

    @abstractmethod
    async def load_discovery(self, user_id: str, session_id: str) -> McpState | None: ...

    @abstractmethod
    async def update_discovery(self, state: McpState) -> None: ...

    @abstractmethod
    async def delete_discovery(self, user_id: str, session_id: str) -> None: ...

    @abstractmethod
    async def mark_completed(self, user_id: str, session_id: str) -> None: ...

    @abstractmethod
    async def is_completed(self, user_id: str, session_id: str) -> bool: ...

    @abstractmethod
    async def store_mcp_session(
        self, user_id: str, session_id: str, server_name: str, mcp_session_id: str
    ) -> None: ...

    @abstractmethod
    async def get_mcp_session(
        self, user_id: str, session_id: str, server_name: str
    ) -> str | None: ...

    @abstractmethod
    async def clear_mcp_session(
        self, user_id: str, session_id: str, server_name: str,
        expected_session_id: str | None = None
    ) -> None: ...
```

**Implementations:**

| Class | Storage | Use Case |
|-------|---------|----------|
| `InMemoryStateManager` | Dict with asyncio.Lock | Development, testing |
| `RedisStateManager` | Redis with Lua scripts | Production, horizontal scaling |

**Redis Key Format:** `mcp_state:{user_id}:{session_id}`

**Redis Features:**
- TTL support (default 24 hours)
- Atomic operations via Lua scripts
- JSON serialization

### 3.3 McpPluginRegistry

**Location:** `mcp_plugin_registry.py`

Stateless class with class methods for tool discovery and retrieval.

```python
class McpPluginRegistry:
    @classmethod
    async def discover_and_materialize(
        cls,
        mcp_servers: list[McpServerConfig],
        user_id: str,
        session_id: str,
        discovery_manager: McpStateManager,
        app_config: AppConfig,
    ) -> None:
        """
        Discover tools from MCP servers and store in state manager.

        Flow:
        1. Load/create discovery state
        2. For each server:
           a. Resolve OAuth tokens (pre-flight auth check)
           b. Connect to server
           c. Initialize MCP session
           d. List tools
           e. Register in catalog (governance)
           f. Serialize and store
        3. Mark discovery completed
        4. Raise first AuthRequiredError if any
        """

    @classmethod
    async def get_tools_for_session(
        cls,
        user_id: str,
        session_id: str,
        discovery_manager: McpStateManager,
    ) -> dict[str, list[McpTool]]:
        """
        Get discovered tools for a session.

        Returns: {server_name: [McpTool, ...]}
        """

    @classmethod
    def _register_tool_in_catalog(
        cls,
        tool_info: Tool,
        server_config: McpServerConfig,
    ) -> None:
        """Register tool in PluginCatalog for governance/HITL."""

    @classmethod
    def _serialize_plugin_data(
        cls,
        tools: list[McpTool],
        server_name: str,
        server_config: McpServerConfig,
    ) -> dict:
        """Serialize tools for external storage (secrets stripped)."""
```

### 3.4 McpConnectionManager

**Location:** `mcp_client.py`

Request-scoped connection manager with lazy connection creation.

```python
class McpConnectionManager:
    def __init__(
        self,
        server_configs: dict[str, McpServerConfig],
        user_id: str,
        session_id: str,
        state_manager: McpStateManager,
        app_config: AppConfig,
    ):
        self._server_configs = server_configs
        self._user_id = user_id
        self._session_id = session_id
        self._state_manager = state_manager
        self._app_config = app_config

        # Runtime state
        self._sessions: dict[str, ClientSession] = {}
        self._get_session_id_callbacks: dict[str, Callable] = {}
        self._stored_session_ids: dict[str, str] = {}
        self._connection_stack = AsyncExitStack()

    async def __aenter__(self) -> "McpConnectionManager":
        """
        Enter context: Load stored MCP session IDs.
        """
        for server_name in self._server_configs:
            stored_id = await self._state_manager.get_mcp_session(
                self._user_id, self._session_id, server_name
            )
            if stored_id:
                self._stored_session_ids[server_name] = stored_id
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Exit context: Persist session IDs and close connections.
        """
        # Persist MCP session IDs for servers that were connected
        for server_name, get_session_id in self._get_session_id_callbacks.items():
            current_id = get_session_id()
            if current_id:
                await self._state_manager.store_mcp_session(
                    self._user_id, self._session_id, server_name, current_id
                )

        # Close all connections
        await self._connection_stack.__aexit__(exc_type, exc_val, exc_tb)

    async def get_or_create_session(self, server_name: str) -> ClientSession:
        """
        Get existing session or create new one (lazy).

        Sessions are reused within the request scope.
        """
        if server_name in self._sessions:
            return self._sessions[server_name]

        server_config = self._server_configs[server_name]

        session, get_session_id = await create_mcp_session_with_retry(
            server_config,
            self._connection_stack,
            self._user_id,
            mcp_session_id=self._stored_session_ids.get(server_name),
            on_stale_session=self._create_stale_handler(server_name),
            app_config=self._app_config,
        )

        self._sessions[server_name] = session
        self._get_session_id_callbacks[server_name] = get_session_id

        return session
```

### 3.5 McpTool

**Location:** `mcp_client.py`

Stateless tool wrapper that stores configuration for invocation.

```python
class McpTool:
    def __init__(
        self,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any] | None,
        server_config: McpServerConfig,
        server_name: str,
    ):
        self.tool_name = tool_name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.server_config = server_config  # Sanitized (no secrets)
        self.server_name = server_name

    async def invoke(
        self,
        connection_manager: McpConnectionManager,
        **kwargs: Any,
    ) -> str:
        """
        Invoke tool via connection manager.

        1. Validate inputs against JSON schema
        2. Get/create session via connection manager
        3. Execute tool
        4. Parse result to string
        """
        self._validate_inputs(kwargs)

        session = await connection_manager.get_or_create_session(self.server_name)

        result = await session.call_tool(self.tool_name, kwargs)

        return self._parse_result(result)

    def _validate_inputs(self, kwargs: dict) -> None:
        """Validate inputs against JSON schema."""
        # Check required properties
        required = self.input_schema.get("required", [])
        for prop in required:
            if prop not in kwargs:
                raise ValueError(f"Missing required parameter: {prop}")

    def _parse_result(self, result: CallToolResult) -> str:
        """Parse MCP result to string."""
        if result.isError:
            error_text = "\n".join(
                c.text for c in result.content if hasattr(c, "text")
            )
            raise RuntimeError(f"MCP tool error: {error_text}")

        return "\n".join(
            c.text for c in result.content if hasattr(c, "text")
        )
```

### 3.6 McpPlugin

**Location:** `mcp_client.py`

Semantic Kernel plugin wrapper that dynamically creates kernel functions.

```python
class McpPlugin(BasePlugin):
    def __init__(
        self,
        tools: list[McpTool],
        server_name: str,
        user_id: str,
        connection_manager: McpConnectionManager,
    ):
        if not user_id:
            raise ValueError("MCP plugins require user_id for OAuth2 resolution")
        if not connection_manager:
            raise ValueError("MCP plugins require connection_manager")

        self.server_name = server_name
        self.user_id = user_id
        self.connection_manager = connection_manager

        # Dynamically add kernel functions for each tool
        for tool in tools:
            self._add_tool_function(tool)

    def _add_tool_function(self, tool: McpTool) -> None:
        """Create @kernel_function method for tool."""

        @kernel_function(
            name=f"{self.server_name}_{tool.tool_name}",
            description=tool.description,
        )
        async def tool_function(**kwargs: Any) -> str:
            return await tool.invoke(
                connection_manager=self.connection_manager,
                **kwargs,
            )

        # Set parameter metadata from JSON schema
        tool_function.__kernel_function_parameters__ = self._build_parameters(
            tool.input_schema
        )

        # Add as instance method
        sanitized_name = self._sanitize_name(tool.tool_name)
        setattr(self, sanitized_name, tool_function)

    def _build_parameters(self, input_schema: dict) -> list[dict]:
        """Convert JSON schema to Semantic Kernel parameter format."""
        parameters = []
        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])

        for name, prop in properties.items():
            parameters.append({
                "name": name,
                "description": prop.get("description", ""),
                "type": self._json_type_to_python(prop.get("type")),
                "required": name in required,
                "default_value": prop.get("default"),
            })

        return parameters
```

## 4. Authentication

### 4.1 OAuth 2.1 Implementation

**Location:** `auth/oauth_client.py`

```python
class OAuthClient:
    async def initiate_authorization_flow(
        self,
        server_config: McpServerConfig,
        user_id: str,
    ) -> str:
        """
        Initiate OAuth authorization flow.

        1. Discover Protected Resource Metadata (RFC 9728)
        2. Determine if resource parameter needed (protocol version check)
        3. Generate PKCE pair (verifier, challenge)
        4. Generate state (CSRF protection)
        5. Store flow state
        6. Discover auth server metadata (RFC 8414)
        7. Try dynamic client registration (RFC 7591) if no client_id
        8. Build authorization URL

        Returns: Authorization URL for user redirect
        """

    async def handle_callback(
        self,
        code: str,
        state: str,
        user_id: str,
        server_config: McpServerConfig,
    ) -> OAuth2AuthData:
        """
        Handle OAuth callback after user authorization.

        1. Validate state (CSRF + user_id match)
        2. Exchange code for tokens (with PKCE verifier)
        3. Validate scopes (prevent escalation)
        4. Store tokens in AuthStorage
        5. Clean up flow state

        Returns: Stored OAuth2AuthData
        """

    async def refresh_access_token(
        self,
        refresh_request: RefreshTokenRequest,
    ) -> TokenResponse:
        """Refresh expired access token."""

    @staticmethod
    def validate_token_scopes(
        requested_scopes: list[str] | None,
        token_response: TokenResponse,
    ) -> None:
        """
        Validate that returned scopes don't exceed requested scopes.

        Prevents scope escalation attacks per OAuth 2.1 Section 3.3.
        """
```

### 4.2 Token Resolution

**Location:** `mcp_client.py`

```python
async def resolve_server_auth_headers(
    server_config: McpServerConfig,
    user_id: str | None = None,
    app_config: AppConfig | None = None,
) -> dict[str, str]:
    """
    Resolve authentication headers for MCP server.

    Priority:
    1. User ID header injection (if configured)
    2. Static headers (non-Authorization)
    3. OAuth token from AuthStorage

    Raises:
        AuthRequiredError: If OAuth configured but no token available
    """
    headers = {}

    # User ID injection
    if server_config.user_id_header and user_id:
        headers[server_config.user_id_header] = user_id

    # Static headers (filter out Authorization if OAuth configured)
    if server_config.headers:
        for k, v in server_config.headers.items():
            if k.lower() != "authorization" or not server_config.auth_server:
                headers[k] = v

    # OAuth token resolution
    if server_config.auth_server and server_config.scopes:
        auth_storage = AuthStorageFactory(app_config).get_auth_storage_manager()
        composite_key = build_auth_storage_key(
            server_config.auth_server,
            server_config.scopes
        )

        auth_data = auth_storage.retrieve(user_id, composite_key)

        if not auth_data:
            raise AuthRequiredError(
                server_name=server_config.name,
                auth_server=server_config.auth_server,
                scopes=server_config.scopes,
            )

        # Validate token
        resource_uri = server_config.effective_canonical_uri
        if not auth_data.is_valid_for_resource(resource_uri):
            # Try refresh
            if auth_data.refresh_token:
                # ... refresh logic ...
                pass
            else:
                raise AuthRequiredError(...)

        headers["Authorization"] = f"Bearer {auth_data.access_token}"

    return headers
```

### 4.3 Auth Storage Key

```python
def build_auth_storage_key(auth_server: str, scopes: list[str]) -> str:
    """
    Build composite key for auth storage.

    Format: {auth_server}|{sorted_scopes}

    Scopes are sorted for consistency:
    - ["write", "read"] → "read|write"
    """
    sorted_scopes = sorted(scopes)
    return f"{auth_server}|{'|'.join(sorted_scopes)}"
```

## 5. Governance

### 5.1 Governance Mapping

**Location:** `mcp_client.py`

```python
def map_mcp_annotations_to_governance(
    annotations: dict[str, Any],
    tool_description: str = "",
) -> Governance:
    """
    Map MCP tool annotations to governance policy.

    SECURE-BY-DEFAULT: Start with HITL required, relax only with
    explicit safe annotations.
    """
    requires_hitl = True
    cost = "high"
    data_sensitivity = "sensitive"

    # Relax for explicit read-only
    if annotations.get("readOnlyHint"):
        requires_hitl = False
        cost = "low"
        data_sensitivity = "public"

    # Strengthen for explicit destructive
    if annotations.get("destructiveHint"):
        requires_hitl = True
        cost = "high"
        data_sensitivity = "sensitive"

    # Check description for high-risk keywords
    high_risk_keywords = [
        "http", "network", "api", "file", "execute", "database",
        "delete", "remove", "modify", "write", "create", "send",
    ]
    description_lower = tool_description.lower()
    if any(kw in description_lower for kw in high_risk_keywords):
        requires_hitl = True

    return Governance(
        requires_hitl=requires_hitl,
        cost=cost,
        data_sensitivity=data_sensitivity,
    )
```

### 5.2 Trust Level Application

```python
def apply_trust_level_governance(
    base_governance: Governance,
    trust_level: str,
    tool_description: str = "",
) -> Governance:
    """
    Apply trust level to base governance.

    Trust levels:
    - untrusted: Force HITL for ALL tools
    - sandboxed: Elevated restrictions
    - trusted: Use annotation-based (with defense-in-depth)
    """
    if trust_level == "untrusted":
        return Governance(
            requires_hitl=True,
            cost="high",
            data_sensitivity="sensitive",
        )

    if trust_level == "sandboxed":
        return Governance(
            requires_hitl=True,
            cost=base_governance.cost,
            data_sensitivity=base_governance.data_sensitivity,
        )

    # trusted: Check for high-risk even on trusted servers
    if _has_high_risk_indicators(tool_description):
        return Governance(
            requires_hitl=True,
            cost="high",
            data_sensitivity="sensitive",
        )

    return base_governance
```

### 5.3 Governance Overrides

```python
def apply_governance_overrides(
    base_governance: Governance,
    tool_name: str,
    overrides: dict[str, GovernanceOverride] | None,
) -> Governance:
    """
    Apply per-tool governance overrides.

    Overrides take precedence over base governance.
    Only specified fields are overridden.
    """
    if not overrides or tool_name not in overrides:
        return base_governance

    override = overrides[tool_name]

    return Governance(
        requires_hitl=(
            override.requires_hitl
            if override.requires_hitl is not None
            else base_governance.requires_hitl
        ),
        cost=override.cost or base_governance.cost,
        data_sensitivity=override.data_sensitivity or base_governance.data_sensitivity,
    )
```

## 6. Handler Integration

### 6.1 Session Discovery

**Location:** `tealagents/v1alpha1/agent/handler.py`

```python
async def _ensure_session_discovery(
    self,
    user_id: str,
    session_id: str,
    task_id: str,
    request_id: str,
) -> AuthChallengeResponse | None:
    """
    Ensure MCP discovery is completed for session.

    Returns AuthChallengeResponse if authentication required.
    """
    # Check if already completed
    if await self.discovery_manager.is_completed(user_id, session_id):
        return None

    # Create state if needed
    state = await self.discovery_manager.load_discovery(user_id, session_id)
    if not state:
        state = McpState(
            user_id=user_id,
            session_id=session_id,
            discovered_servers={},
            discovery_completed=False,
        )
        await self.discovery_manager.create_discovery(state)

    # Run discovery
    try:
        await McpPluginRegistry.discover_and_materialize(
            self.config.get_agent().mcp_servers,
            user_id,
            session_id,
            self.discovery_manager,
            self.app_config,
        )
        await self.discovery_manager.mark_completed(user_id, session_id)
        return None

    except AuthRequiredError as e:
        # Generate OAuth authorization URL
        auth_url = await self.oauth_client.initiate_authorization_flow(
            self._get_server_config(e.server_name),
            user_id,
        )

        return AuthChallengeResponse(
            session_id=session_id,
            task_id=task_id,
            auth_challenges=[{
                "server_name": e.server_name,
                "auth_server": e.auth_server,
                "scopes": e.scopes,
                "auth_url": auth_url,
            }],
            resume_url=f"/tealagents/v1alpha1/invoke",
        )
```

### 6.2 Request Execution

```python
async def invoke(self, auth_token: str, inputs: dict) -> AgentResponse:
    # 1. Authenticate user
    user_id = await self.authenticate_user(auth_token)
    session_id, task_id, request_id = self._handle_state_ids(inputs)

    # 2. MCP Discovery (once per session)
    if self.config.get_agent().mcp_servers:
        auth_challenge = await self._ensure_session_discovery(
            user_id, session_id, task_id, request_id
        )
        if auth_challenge:
            return auth_challenge

    # 3. Create request-scoped connection manager
    connection_manager = await self._create_mcp_connection_manager(
        user_id, session_id
    )

    # 4. Execute with connection manager context
    if connection_manager:
        async with connection_manager:
            return await self._execute_agent(
                inputs, user_id, session_id, connection_manager
            )
    else:
        return await self._execute_agent(inputs, user_id, session_id)
```

## 7. File Structure

```
src/sk_agents/
├── mcp_client.py                    # Core MCP client (McpTool, McpPlugin, McpConnectionManager)
├── mcp_plugin_registry.py           # Tool discovery and registration
├── mcp_discovery/
│   ├── __init__.py
│   ├── mcp_discovery_manager.py     # Abstract McpStateManager
│   ├── in_memory_discovery_manager.py
│   ├── redis_discovery_manager.py
│   └── discovery_manager_factory.py
├── auth/
│   ├── oauth_client.py              # OAuth 2.1 client
│   ├── oauth_models.py              # Request/response models
│   ├── oauth_pkce.py                # PKCE implementation
│   ├── oauth_state_manager.py       # Flow state management
│   ├── server_metadata.py           # RFC 8414/9728 discovery
│   └── client_registration.py       # RFC 7591 dynamic registration
├── auth_storage/
│   ├── models.py                    # OAuth2AuthData model
│   ├── auth_storage_factory.py
│   ├── in_memory_secure_auth_storage_manager.py
│   └── secure_auth_storage_manager.py
├── tealagents/v1alpha1/
│   ├── config.py                    # McpServerConfig, GovernanceOverride
│   ├── agent/handler.py             # Handler with MCP integration
│   └── kernel_builder.py            # load_mcp_plugins()
└── plugin_catalog/
    ├── models.py                    # Governance, PluginTool
    └── local_plugin_catalog.py      # Catalog with dynamic registration
```

## 8. Security Considerations

| Concern | Mitigation |
|---------|------------|
| Token storage | Encrypted storage with user isolation |
| Secret serialization | Secrets stripped before state storage |
| HTTPS enforcement | OAuth requires HTTPS by default |
| Scope escalation | validate_token_scopes() checks |
| CSRF protection | State parameter in OAuth flow |
| Trust boundaries | Trust levels with HITL requirements |
| Session hijacking | MCP session IDs scoped to user+session |

## 9. Known Limitations

1. **OAuth 2.1 E2E Testing**: Implementation complete but not tested with real OAuth providers
2. **stdio Transport**: Supported but not primary focus
3. **WebSocket Transport**: Not supported (pending MCP SDK)
4. **Tool Hot-Reload**: Tools discovered at session start only
5. **Connection Pooling**: Within request only, not cross-request

## 10. Future Enhancements

| Priority | Enhancement |
|----------|-------------|
| P1 | E2E OAuth testing with real providers |
| P1 | Connection health monitoring |
| P2 | Cross-request connection pooling |
| P2 | Tool hot-reload |
| P3 | WebSocket transport |
| P3 | stdio transport hardening |
