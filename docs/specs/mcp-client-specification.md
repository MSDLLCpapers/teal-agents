# MCP Client Integration - Design & Implementation Specification

**Version:** 1.0  
**Date:** 2025-01-09  
**Status:** Implemented  

## 1. Overview

This specification describes the design and implementation of Model Context Protocol (MCP) client integration for the Teal Agents platform. The integration supports multiple transport protocols (stdio, WebSocket, HTTP) and allows agents to automatically connect to MCP servers, discover their tools, and register them as Semantic Kernel plugins.

### 1.1 Goals

- **Seamless Integration**: MCP tools should work identically to native plugins
- **Configuration-Driven**: Server connections specified via agent configuration
- **Automatic Discovery**: Tools are discovered and registered without manual intervention
- **Error Resilience**: Failed connections shouldn't prevent agent initialization
- **Resource Management**: Proper connection lifecycle handling

### 1.2 Non-Goals

- Authentication/authorization for MCP servers (future enhancement)
- Real-time tool discovery (tools discovered at connection time only)
- MCP server management/orchestration

## 2. Architecture

### 2.1 Component Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Agent Config  │───▶│   KernelBuilder  │───▶│ Semantic Kernel │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │              ┌─────────────────┐              │
         │              │   McpClient     │              │
         └─────────────▶│                 │◀─────────────┘
                        │ - connect()     │
                        │ - discover()    │
                        │ - register()    │
                        └─────────────────┘
                                 │
                    ┌─────────────────────────────┐
                    │        MCP Servers          │
                    │                             │
                    │ ┌─────────┐ ┌─────────────┐ │
                    │ │FileSystem│ │   SQLite   │ │
                    │ │ Server  │ │   Server   │ │
                    │ └─────────┘ └─────────────┘ │
                    └─────────────────────────────┘
```

### 2.2 Core Components

1. **McpClient**: Main orchestrator for MCP server connections
2. **McpTool**: Wrapper that adapts MCP tools to Semantic Kernel functions
3. **McpPlugin**: Plugin container for MCP tools
4. **McpServerConfig**: Configuration model for server specifications
5. **KernelBuilder**: Extended to support MCP server loading

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
    name: str                                    # Unique server identifier
    transport: Literal["stdio", "websocket", "http"] = "stdio"  # Transport protocol
    
    # Stdio transport fields
    command: Optional[str] = None               # Command to start server
    args: List[str] = []                       # Command arguments  
    env: Optional[Dict[str, str]] = None       # Environment variables
    
    # WebSocket transport fields
    url: Optional[str] = None                  # WebSocket URL
    headers: Optional[Dict[str, str]] = None   # WebSocket headers
    
    # HTTP transport fields
    base_url: Optional[str] = None             # HTTP base URL
    api_key: Optional[str] = None              # API key for authentication
    timeout: Optional[int] = 30                # Request timeout
```

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

#### 3.3.2 Kernel Builder Integration

Extended `KernelBuilder.build_kernel()` method:

```python
def build_kernel(
    self,
    model_name: str,
    service_id: str,
    plugins: list[str],
    remote_plugins: list[str],
    mcp_servers: list[McpServerConfig] | None = None,  # New parameter
    authorization: str | None = None,
    extra_data_collector: ExtraDataCollector | None = None,
) -> Kernel:
    # ... existing logic
    kernel = asyncio.run(self._load_mcp_plugins(mcp_servers, kernel))
    return kernel
```

## 4. Configuration Specification

### 4.1 Agent Configuration Schema

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
  
  # New: MCP server configurations with multiple transports
  mcp_servers:
    # Stdio transport
    - name: local-server
      transport: stdio               # Optional, defaults to stdio
      command: executable-path       # Required for stdio
      args: ["arg1", "arg2"]        # Optional: command arguments
      env:                          # Optional: environment variables
        VAR_NAME: "value"
        
    # WebSocket transport
    - name: websocket-server
      transport: websocket
      url: "wss://example.com/mcp"   # Required for websocket
      headers:                      # Optional: WebSocket headers
        Authorization: "Bearer TOKEN"
        
    # HTTP transport
    - name: http-server
      transport: http
      base_url: "https://api.example.com/v1"  # Required for http
      api_key: "${API_KEY}"         # Optional: API key
      timeout: 30                   # Optional: timeout in seconds
      headers:                      # Optional: custom headers
        X-Client-Version: "1.0"
```

### 4.2 Example Configurations

#### Filesystem Server
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

#### SQLite Server
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

#### Custom Server with Environment
```yaml
mcp_servers:
  - name: custom-api
    command: /opt/custom-mcp-server
    args: ["--port", "8080", "--config", "/etc/server.conf"]
    env:
      API_KEY: "${API_KEY}"
      LOG_LEVEL: "INFO"
```

## 5. Deployment Considerations

### 5.1 Dependencies

**Base Dependency:**
- `mcp>=1.0.0` - Model Context Protocol client library with stdio support

**Optional Transport Dependencies:**
- `mcp[websocket]>=1.0.0` - For WebSocket transport support
- `mcp[http]>=1.0.0` - For HTTP transport support
- `mcp[websocket,http]>=1.0.0` - For all transport types

**Installation:**
```bash
# Base installation (stdio only)
uv add "mcp>=1.0.0"

# With WebSocket support
uv add "mcp[websocket]>=1.0.0"

# With HTTP support
uv add "mcp[http]>=1.0.0"

# With all transports
uv add "mcp[websocket,http]>=1.0.0"
```

### 5.2 Runtime Requirements

1. **Python Version**: 3.12+ (existing requirement)
2. **MCP Server Executables**: Must be available in the environment
3. **Permissions**: File system access for MCP server executables
4. **Network**: If MCP servers require network access

### 5.3 Environment Variables

MCP servers may require environment variables. These can be:
- Specified in the `env` field of `McpServerConfig`
- Inherited from the agent's environment
- Passed through container orchestration

## 6. Error Handling & Resilience

### 6.1 Connection Failures

- **Behavior**: Log transport-specific error, continue with other servers
- **Agent Impact**: Agent starts successfully without failed server's tools
- **Error Context**: Transport-specific error messages (stdio: command issues, websocket: SSL/connection, http: authentication/endpoints)
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
- ✅ McpServerConfig configuration model with transport support
- ✅ Transport factory pattern (McpTransportFactory)
- ✅ Stdio, WebSocket, and HTTP transport implementations
- ✅ KernelBuilder integration for MCP loading
- ✅ AgentBuilder updates to pass MCP configuration

### Configuration & Examples
- ✅ Extended AgentConfig with mcp_servers field
- ✅ Multi-transport example configurations
- ✅ Stdio, WebSocket, and HTTP specific examples
- ✅ Documentation and integration guide with transport details
- ✅ Added mcp dependency with transport options to pyproject.toml

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