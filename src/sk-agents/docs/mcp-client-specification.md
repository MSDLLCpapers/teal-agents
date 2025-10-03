# MCP Client Integration - Design & Implementation Specification

**Version:** 2.0
**Date:** 2025-10-02

## 1. Overview

This specification describes the design and implementation of Model Context Protocol (MCP) client integration for the Teal Agents platform. The integration supports multiple transport protocols (stdio and HTTP) and uses a **stateless architecture** where plugin classes are materialized at session start, then instantiated per-request without persistent connections.

**Latest Update:** Complete refactoring to stateless plugin registry architecture. Removed ~450 lines of deprecated connection management code. MCP tools now work identically to non-MCP tools with temporary connections for discovery and execution.

### 1.1 Goals

- **Seamless Integration**: MCP tools should work identically to native plugins
- **Stateless Architecture**: No persistent connections, temporary connections for discovery and execution
- **Pattern Alignment**: Follow established ephemeral agent-per-request patterns
- **Configuration-Driven**: Server connections specified via agent configuration
- **Automatic Discovery**: Tools discovered at session start and materialized as plugin classes
- **Authentication Integration**: Leverage existing OAuth2 auth infrastructure
- **Tool Governance**: Full HITL and governance policy integration
- **Error Resilience**: Failed connections shouldn't prevent agent initialization
- **Resource Management**: Python `async with` ensures automatic cleanup

### 1.2 Non-Goals

- Real-time tool discovery (tools discovered at session start only)
- MCP server management/orchestration
- Persistent connections (all connections are temporary)

## 2. Architecture

### 2.1 Component Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      SESSION START                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ McpPluginRegistry.discover_and_materialize()         │   │
│  │   - Temp connect to MCP servers                      │   │
│  │   - Discover tools & register in catalog             │   │
│  │   - Create McpPlugin CLASSES with stateless McpTools│   │
│  │   - Close connections                                │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   PER-REQUEST (AGENT BUILD)                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ KernelBuilder.load_mcp_plugins()                     │   │
│  │   - Get plugin CLASS from registry                   │   │
│  │   - Instantiate plugin (no connection)               │   │
│  │   - Add to kernel                                    │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                 TOOL INVOCATION (STATELESS)                 │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ McpTool.invoke()                                     │   │
│  │   - Create temp connection                           │   │
│  │   - Execute tool                                     │   │
│  │   - Close connection (automatic)                     │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Core Components

1. **McpPluginRegistry**: Materializes plugin classes at session start (stateless discovery)
2. **McpTool**: Stateless tool wrapper that stores config (not connections)
3. **McpPlugin**: Plugin container with type annotations from JSON schema
4. **McpServerConfig**: Configuration model with authentication and governance fields
5. **KernelBuilder**: Instantiates plugins from registry at agent build time
6. **AgentHandler**: Triggers MCP discovery at session start

## 3. Implementation Details

### 3.1 File Structure

```
src/sk_agents/
├── mcp_client.py                           # Main MCP client implementation
├── tealagents/v1alpha1/
│   ├── config.py                          # Extended with McpServerConfig
│   ├── agent_builder.py                   # Updated to pass MCP config
│   └── kernel_builder.py                  # Extended with MCP loading
└── pyproject.toml                         # Added mcp>=1.0.0 dependency

docs/
├── mcp-integration.md                     # User documentation
└── specs/
    └── mcp-client-specification.md        # This document

examples/
└── mcp-agent-config.yaml                 # Example configuration
```

### 3.2 Key Classes

#### 3.2.1 McpServerConfig

```python
class McpServerConfig(BaseModel):
    """Configuration for an MCP server connection supporting multiple transports."""
    model_config = ConfigDict(extra="allow")

    # Universal fields
    name: str                                             # Unique server identifier
    transport: Optional[Literal["stdio", "http"]] = None  # Inferred if omitted

    # Stdio transport fields
    command: Optional[str] = None               # Command to start server
    args: List[str] = []                        # Command arguments
    env: Optional[Dict[str, str]] = None        # Environment variables

    # HTTP transport fields (supports both Streamable HTTP and SSE)
    url: Optional[str] = None                   # HTTP/SSE endpoint URL
    headers: Optional[Dict[str, str]] = None    # HTTP headers (for auth, etc.)
    timeout: Optional[float] = None             # Connection timeout in seconds
    sse_read_timeout: Optional[float] = None    # SSE read timeout in seconds

    # Authentication integration fields
    auth_server: Optional[str] = None           # OAuth2 authorization server URL
    scopes: List[str] = []                      # Required OAuth2 scopes for tools

    # Tool governance override fields
    tool_governance_overrides: Optional[Dict[str, GovernanceOverride]] = None
```

Transport inference:
- If `url` provided (and `command` not) → http
- If `command` provided (and `url` not) → stdio
- If both provided without `transport` → validation error

#### 3.2.2 McpClient

```python
class McpClient:
    """Main MCP client for managing server connections."""
    
    # Core Methods
    async def connect_server(self, server_config: McpServerConfig) -> None
    async def disconnect_server(self, server_name: str) -> None
    def get_plugin(self, server_name: str) -> Optional[McpPlugin]
    def register_plugins_with_kernel(self, kernel: Kernel) -> None
    
    # Internal State
    connected_servers: Dict[str, ClientSession]
    server_configs: Dict[str, McpServerConfig]
    plugins: Dict[str, McpPlugin]
```

#### 3.2.3 McpTool

```python
class McpTool:
    """Wrapper for MCP tools to make them compatible with Semantic Kernel."""
    
    name: str                              # Tool name
    description: str                       # Tool description
    input_schema: Dict[str, Any]           # JSON schema for inputs
    client_session: ClientSession          # MCP session reference
    
    async def invoke(self, **kwargs) -> str
```

#### 3.2.4 McpPlugin

```python
class McpPlugin(BasePlugin):
    """Plugin wrapper that holds MCP tools for Semantic Kernel integration."""
    
    tools: List[McpTool]
    
    def _add_tool_function(self, tool: McpTool)  # Dynamically adds @kernel_function
```

### 3.3 Integration Points

#### 3.3.1 Agent Configuration

Extended `AgentConfig` to include MCP servers:

```python
class AgentConfig(BaseModel):
    # Existing fields...
    mcp_servers: list[McpServerConfig] | None = None
```

#### 3.3.2 Handler-Driven MCP Loading

MCP loading now happens after agent construction in async context:

```python
# In agent handler, after agent construction
agent = self.agent_builder.build_agent(self.config.get_agent(), ...)

# Load MCP plugins after agent construction to avoid async gap
if self.config.get_agent().mcp_servers:
    await self.agent_builder.kernel_builder.load_mcp_plugins(
        self.config.get_agent().mcp_servers,
        agent.agent.kernel,
        user_id,
        session_id
    )
```

#### KernelBuilder Public API

```python
class KernelBuilder:
    async def load_mcp_plugins(
        self,
        mcp_servers: list[McpServerConfig],
        kernel: Kernel,
        user_id: str,
        session_id: str
    ) -> Kernel:
        """Public async entry point for MCP plugin loading."""
        return await self._load_mcp_plugins(mcp_servers, kernel, user_id, session_id)
```

## 4. Authentication & Authorization

### 4.1 OAuth2 Integration

MCP servers support server-level authentication through the existing OAuth2 infrastructure:

```python
# Authentication configuration
auth_server: "https://github.com/login/oauth"
scopes: ["repo", "read:user"]

# Auth resolution at runtime
def resolve_server_auth_headers(server_config: McpServerConfig, user_id: str) -> Dict[str, str]:
    auth_storage_factory = AuthStorageFactory(app_config)
    auth_storage = auth_storage_factory.get_auth_storage_manager()

    # Generate composite key for OAuth2 token lookup
    composite_key = f"{server_config.auth_server}|{sorted(server_config.scopes)}"
    auth_data = auth_storage.retrieve(user_id, composite_key)

    if auth_data and isinstance(auth_data, OAuth2AuthData):
        return {"Authorization": f"Bearer {auth_data.access_token}"}
```

### 4.2 Auth Challenge Flow

Before agent construction, MCP servers are checked for authentication:

```python
# Pre-flight auth check in handler
auth_challenge = await self.authenticate_mcp_servers(user_id, session_id, task_id, request_id)
if auth_challenge:
    return AuthChallengeResponse(
        auth_challenges=[...],  # List of servers requiring auth
        resume_url="..."        # URL to resume after auth completion
    )
```

### 4.3 Tool Governance Integration

MCP tools integrate with the existing governance system:

```python
# Automatic governance mapping from MCP annotations
def map_mcp_annotations_to_governance(annotations: Dict[str, Any]) -> Governance:
    destructive_hint = annotations.get("destructiveHint", False)
    read_only_hint = annotations.get("readOnlyHint", False)

    return Governance(
        requires_hitl=destructive_hint,
        cost="high" if destructive_hint else ("low" if read_only_hint else "medium"),
        data_sensitivity="sensitive" if destructive_hint else ("public" if read_only_hint else "proprietary")
    )

# Manual governance overrides
tool_governance_overrides:
  create_repository:
    requires_hitl: false  # Override auto-inferred HITL requirement
    cost: "medium"        # Override auto-inferred cost level
```

## 5. Configuration Specification

### 5.1 Agent Configuration Schema

```yaml
apiVersion: tealagents/v1alpha1
name: agent-name
version: "1.0"
spec:
  name: agent-name
  model: model-name
  system_prompt: "Agent instructions..."
  
  # Optional: existing plugin types
  plugins: ["plugin1", "plugin2"]
  remote_plugins: ["https://example.com/api"]
  
  # MCP server configurations with multiple transports
  mcp_servers:
    # Stdio transport (local servers)
    - name: local-server
      command: executable-path       # Required for stdio
      args: ["arg1", "arg2"]        # Optional: command arguments
      env:                          # Optional: environment variables
        VAR_NAME: "value"
        
    # HTTP transport (remote servers)
    - name: http-server
      url: "https://api.example.com/mcp"      # Required: HTTP/SSE endpoint URL
      timeout: 30.0                 # Optional: connection timeout (seconds)
      sse_read_timeout: 300.0       # Optional: SSE read timeout (seconds)
      headers:                      # Optional: HTTP headers for auth/config
        Authorization: "Bearer ${API_KEY}"
        User-Agent: "TealAgents-MCP/1.1"
        X-Client-Version: "1.0"
  
  # Note: Transport is inferred when omitted. Set explicitly only to override or disambiguate.
```

### 5.2 Example Configurations

#### Filesystem Server (Stdio)
```yaml
mcp_servers:
  - name: filesystem
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "/safe/directory"
    env:
      NODE_ENV: production
```

#### SQLite Server (Stdio)
```yaml
mcp_servers:
  - name: sqlite
    command: python
    args:
      - "-m"
      - "mcp_server_sqlite"
      - "--db-path"
      - "/path/to/database.db"
```

#### GitHub MCP Server (HTTP with OAuth2)
```yaml
mcp_servers:
  - name: github
    url: "https://api.github.com/mcp"
    auth_server: "https://github.com/login/oauth"
    scopes: ["repo", "read:user"]
    tool_governance_overrides:
      create_repository:
        requires_hitl: false
        cost: "medium"
      delete_repository:
        requires_hitl: true
        cost: "high"
        data_sensitivity: "sensitive"
```

#### Authenticated API Server (HTTP with Custom Headers)
```yaml
mcp_servers:
  - name: custom-api
    url: "https://api.example.com/mcp"
    headers:
      Authorization: "Bearer ${API_TOKEN}"
      X-API-Version: "v1"
    timeout: 30.0
    auth_server: "https://auth.example.com/oauth2"
    scopes: ["read", "write"]
```

#### Local Server with Environment Variables
```yaml
mcp_servers:
  - name: local-tools
    command: /opt/custom-mcp-server
    args: ["--port", "8080", "--config", "/etc/server.conf"]
    env:
      API_KEY: "${API_KEY}"
      LOG_LEVEL: "INFO"
    tool_governance_overrides:
      system_command:
        requires_hitl: true
        cost: "high"

## 5. Deployment Considerations

### 5.1 Dependencies

**Base Dependency:**
- `mcp>=1.0.0` - Model Context Protocol client library with stdio support

**HTTP Transport Dependencies:**
- `mcp>=1.13.1` - Base MCP SDK with HTTP transport support
- Automatic transport selection: Streamable HTTP → SSE fallback
- No additional transport-specific packages required

**Installation:**
```bash
# Complete installation (stdio + HTTP transports)
pip install "mcp>=1.13.1"

# For development/testing
pip install "mcp[sse]>=1.13.1"

```

### 5.2 HTTP Transport Features

**Implemented Transport Options:**
1. **Streamable HTTP** (preferred): `/mcp` endpoints for production deployments
2. **Server-Sent Events (SSE)** (fallback): `/sse` endpoints for broad compatibility
3. **Automatic Selection**: Client tries streamable HTTP first, falls back to SSE

**Connection Patterns:**
- URLs ending in `/mcp` use streamable HTTP transport
- URLs ending in `/sse` use SSE transport
- Client automatically handles transport negotiation

### 5.3 Runtime Requirements

1. **Python Version**: 3.10+ (MCP SDK requirement)
2. **MCP Server Executables**: Must be available for stdio transport
3. **Network Access**: Required for HTTP transport servers
4. **Permissions**: File system access for stdio servers

### 5.4 Environment Variables

MCP servers may require environment variables. These can be:
- Specified in the `env` field of `McpServerConfig`
- Inherited from the agent's environment
- Passed through container orchestration

## 6. Error Handling & Resilience

### 6.1 Connection Failures

- **Behavior**: Log transport-specific error, continue with other servers
- **Agent Impact**: Agent starts successfully without failed server's tools
- **Error Context**: Transport-specific error messages:
  - **Stdio**: Command not found, permission denied, executable issues
  - **HTTP**: Timeout, connection refused, 401/404/503 responses, authentication failures
- **Retry**: No automatic retry (future enhancement)

### 6.2 Tool Discovery Failures

- **Behavior**: Log warning, server connection maintained
- **Tool Impact**: Server registered but no tools available
- **Fallback**: Graceful degradation

### 6.3 Tool Invocation Errors

- **Behavior**: Propagate error to agent with descriptive message
- **Recovery**: Agent can handle tool failures in prompt logic
- **Logging**: Full error details logged for debugging

## 7. Testing Strategy

### 7.1 Unit Tests

```python
# Test configuration parsing
def test_mcp_server_config_validation()

# Test client connection management
def test_mcp_client_connect_disconnect()

# Test tool wrapper functionality
def test_mcp_tool_invocation()

# Test plugin registration
def test_mcp_plugin_kernel_registration()
```

### 7.2 Integration Tests

```python
# Test end-to-end agent creation with MCP servers
def test_agent_with_mcp_servers()

# Test tool discovery and usage
def test_mcp_tool_discovery_and_execution()

# Test error scenarios
def test_mcp_server_connection_failures()
```

### 7.3 Manual Testing

1. **Server Compatibility**: Test with various MCP server implementations
2. **Configuration Validation**: Test various YAML configurations
3. **Performance Impact**: Measure agent startup time with MCP servers
4. **Error Scenarios**: Test network failures, invalid commands, etc.

## 8. Security Considerations

### 8.1 Server Command Execution

- **Risk**: Arbitrary command execution via `command` field
- **Mitigation**: Validate against allowlist of approved MCP servers
- **Recommendation**: Use container constraints or sandboxing

### 8.2 File System Access

- **Risk**: MCP servers may access file system
- **Mitigation**: Configure servers with minimal required permissions
- **Recommendation**: Use dedicated service accounts with restricted access

### 8.3 Network Access

- **Risk**: MCP servers may make network requests
- **Mitigation**: Network policies to restrict outbound access
- **Recommendation**: Monitor and log network activity

## 9. Monitoring & Observability

### 9.1 Metrics

```python
# Connection metrics
mcp_connections_active          # Current active connections
mcp_connections_total          # Total connection attempts
mcp_connection_failures_total  # Failed connection attempts

# Tool metrics  
mcp_tools_discovered_total     # Tools discovered per server
mcp_tool_invocations_total     # Tool usage count
mcp_tool_errors_total          # Tool invocation failures
```

### 9.2 Logging

```python
# Connection events
logger.info(f"Connecting to MCP server: {server_name}")
logger.info(f"Successfully connected to MCP server: {server_name}")
logger.error(f"Failed to connect to MCP server {server_name}: {error}")

# Tool discovery
logger.info(f"Discovered tool: {tool_name} from server {server_name}")
logger.warning(f"No tools found on MCP server: {server_name}")

# Tool invocation
logger.error(f"Error invoking MCP tool {tool_name}: {error}")
```

### 9.3 Health Checks

```python
def check_mcp_health() -> Dict[str, bool]:
    """Check health of all connected MCP servers."""
    return {
        server_name: client.is_connected(server_name)
        for server_name in client.get_connected_servers()
    }
```

## 10. Future Enhancements

### 10.1 Priority 1 (Next Release)

1. **Enhanced Authentication**: OAuth2 flows, JWT tokens, certificate-based auth
2. **Connection Retry**: Automatic retry with exponential backoff for all transports
3. **Health Monitoring**: Periodic health checks and reconnection for WebSocket/HTTP
4. **Transport Extensions**: gRPC, TCP, and other transport protocols

### 10.2 Priority 2 (Future Releases)

1. **Dynamic Tool Discovery**: Runtime tool discovery and hot-reloading
2. **Tool Governance**: Integration with HITL and authorization systems
3. **Performance Optimization**: Connection pooling, tool result caching
4. **Server Management**: Start/stop MCP servers programmatically

### 10.3 Priority 3 (Long-term)

1. **Tool Marketplace**: Discover and install MCP servers from registry
2. **Custom Protocols**: Support for non-stdio MCP transports
3. **Tool Composition**: Chain MCP tools for complex workflows

## 11. Migration & Rollback

### 11.1 Backward Compatibility

- **Configuration**: `mcp_servers` field is optional - existing configs work unchanged
- **API**: No breaking changes to existing agent APIs
- **Behavior**: Agents without MCP servers behave identically to before

### 11.2 Feature Flags

Consider adding feature flag support:

```yaml
# Environment variable
TA_MCP_ENABLED=true

# Or in configuration
spec:
  experimental:
    mcp_enabled: true
```

### 11.3 Rollback Strategy

1. **Configuration Rollback**: Remove `mcp_servers` from configs
2. **Dependency Rollback**: Remove `mcp>=1.0.0` from pyproject.toml  
3. **Code Rollback**: Revert kernel_builder changes if needed

## 12. Documentation & Training

### 12.1 User Documentation

- ✅ **Integration Guide**: `docs/mcp-integration.md`
- ✅ **Example Configuration**: `examples/mcp-agent-config.yaml`
- 🔄 **API Reference**: Auto-generated from docstrings
- 📋 **Troubleshooting Guide**: Common issues and solutions

### 12.2 Developer Documentation

- ✅ **Architecture Specification**: This document
- 📋 **Code Comments**: Comprehensive inline documentation
- 📋 **Testing Guide**: How to test MCP integration
- 📋 **Contributing Guide**: How to extend MCP support

### 12.3 Operational Documentation  

- 📋 **Deployment Guide**: Production deployment considerations
- 📋 **Monitoring Runbook**: How to monitor and troubleshoot MCP issues
- 📋 **Security Guide**: Security best practices for MCP servers

---

## Appendix A: Implementation Checklist

### Core Implementation
- ✅ McpClient class with multi-transport connection management
- ✅ McpTool wrapper for Semantic Kernel compatibility  
- ✅ McpPlugin container for tool registration
- ✅ McpServerConfig configuration model with HTTP transport support
- ✅ Transport factory pattern with HTTP transport selection
- ✅ Stdio and HTTP transport implementations (Streamable HTTP + SSE)
- ✅ KernelBuilder integration for MCP loading
- ✅ AgentBuilder updates to pass MCP configuration

### Configuration & Examples
- ✅ Extended AgentConfig with mcp_servers field
- ✅ Multi-transport example configurations (stdio + HTTP)
- ✅ Stdio and HTTP specific examples with real-world scenarios
- ✅ Documentation and integration guide with HTTP transport details
- ✅ Updated mcp dependency to support HTTP transports

### Error Handling
- ✅ Transport-specific connection failure handling
- ✅ Tool discovery error handling
- ✅ Tool invocation error propagation with transport context
- ✅ Comprehensive logging with transport information
- ✅ Dependency validation with helpful error messages

### Documentation
- ✅ User integration guide
- ✅ Example configurations
- ✅ Architecture specification
- ✅ Inline code documentation

## Appendix B: Code Review Checklist

### Functionality
- [ ] MCP servers connect successfully
- [ ] Tools are discovered and registered correctly
- [ ] Tool invocation works with various input types
- [ ] Error scenarios are handled gracefully
- [ ] Configuration validation works properly

### Code Quality
- [ ] Follows existing code style and patterns
- [ ] Comprehensive error handling and logging
- [ ] Proper async/await usage
- [ ] Type hints are complete and accurate
- [ ] Docstrings follow project conventions

### Integration
- [ ] Backward compatibility maintained
- [ ] No breaking changes to existing APIs
- [ ] Follows existing plugin patterns
- [ ] Integrates cleanly with kernel builder

### Testing
- [ ] Unit tests cover core functionality
- [ ] Integration tests verify end-to-end workflows
- [ ] Error scenarios are tested
- [ ] Performance impact is acceptable

### Documentation
- [ ] User documentation is clear and complete
- [ ] Code is well-documented with inline comments
- [ ] Examples work as documented
- [ ] Troubleshooting information is provided
