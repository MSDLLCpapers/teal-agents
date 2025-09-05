# MCP Integration for Teal Agents

The Teal Agents platform now supports integration with Model Context Protocol (MCP) servers using multiple transport protocols, allowing agents to automatically discover and use tools from external MCP servers via stdio, WebSocket, or HTTP connections.

## Overview

The MCP client implementation provides:

- **Automatic tool discovery**: Connect to MCP servers and automatically register their tools
- **Seamless integration**: MCP tools work like native plugins in the Semantic Kernel framework
- **Configuration-driven**: Specify MCP servers in your agent configuration
- **Error handling**: Graceful handling of connection failures and tool invocation errors

## Configuration

Teal Agents supports three MCP transport types:
- **stdio**: Local subprocess communication (default)
- **websocket**: Real-time WebSocket connections
- **http**: REST API communication

To use MCP servers with your agent, add the `mcp_servers` configuration to your agent config:

```yaml
apiVersion: tealagents/v1alpha1
name: my-agent
version: 1.0
spec:
  name: my-agent
  model: gpt-4
  system_prompt: "You are a helpful assistant with access to external tools."
  
  # Regular plugins (optional)
  plugins:
    - calculator
    - weather
  
  # Remote plugins (optional)
  remote_plugins:
    - https://example.com/plugins/api
  
  # MCP servers with different transports
  mcp_servers:
    # Stdio transport (local subprocess)
    - name: filesystem
      transport: stdio  # Optional, defaults to stdio
      command: npx
      args:
        - "@modelcontextprotocol/server-filesystem"
        - "/path/to/allowed/directory"
      env:
        NODE_ENV: production
    
    # WebSocket transport (real-time connection)
    - name: remote-api
      transport: websocket
      url: "wss://mcp-api.example.com/ws"
      headers:
        Authorization: "Bearer ${API_TOKEN}"
        
    # HTTP transport (REST API)
    - name: user-service
      transport: http
      base_url: "https://api.example.com/v1"
      api_key: "${USER_API_KEY}"
      timeout: 30
```

## MCP Server Configuration

### Universal Fields

All MCP servers require:
- **name**: Unique identifier for the server
- **transport**: Protocol type (`stdio`, `websocket`, or `http`) - defaults to `stdio`

### Stdio Transport Fields

For local subprocess communication:
- **command**: Command to start the MCP server (required)
- **args**: Command line arguments (optional)
- **env**: Environment variables (optional)

### WebSocket Transport Fields

For real-time WebSocket connections:
- **url**: WebSocket URL starting with `ws://` or `wss://` (required)
- **headers**: HTTP headers for WebSocket handshake (optional)

### HTTP Transport Fields

For REST API communication:
- **base_url**: Base URL for HTTP requests starting with `http://` or `https://` (required)
- **api_key**: API key for Bearer token authentication (optional)
- **timeout**: Request timeout in seconds (optional, default: 30)
- **headers**: Custom HTTP headers (optional)

## Example MCP Servers

### Stdio Transport Examples

#### Filesystem Server
```yaml
mcp_servers:
  - name: filesystem
    transport: stdio
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "/safe/directory"
```

#### SQLite Server
```yaml
mcp_servers:
  - name: sqlite
    transport: stdio
    command: python
    args:
      - "-m"
      - "mcp_server_sqlite"
      - "--db-path"
      - "/path/to/data.db"
```

### WebSocket Transport Examples

#### Real-time Database
```yaml
mcp_servers:
  - name: realtime-db
    transport: websocket
    url: "wss://db.example.com/mcp/realtime"
    headers:
      Authorization: "Bearer ${DB_TOKEN}"
      X-Database: "production"
```

#### Live Data Feed
```yaml
mcp_servers:
  - name: data-stream
    transport: websocket
    url: "wss://stream.example.com/mcp"
    headers:
      X-API-Key: "${STREAM_KEY}"
```

### HTTP Transport Examples

#### User Management API
```yaml
mcp_servers:
  - name: user-api
    transport: http
    base_url: "https://api.example.com/users/v1"
    api_key: "${USER_API_KEY}"
    timeout: 30
    headers:
      X-Service-Version: "v1.2"
```

#### Analytics Service
```yaml
mcp_servers:
  - name: analytics
    transport: http
    base_url: "https://analytics.example.com/api/v2"
    timeout: 60
    headers:
      Authorization: "Bearer ${ANALYTICS_TOKEN}"
      Content-Type: "application/json"
```

## Tool Usage

Once configured, MCP tools are automatically available to your agent. They appear in the kernel with the prefix `mcp_<server_name>_<tool_name>`.

For example, if you have a filesystem server named "filesystem" with a "read_file" tool, it would be registered as `mcp_filesystem_read_file`.

## Error Handling

The MCP client includes robust error handling:

- **Connection failures**: If a server cannot be connected to, other servers will still be loaded
- **Tool discovery failures**: Logged but don't prevent agent initialization
- **Tool invocation errors**: Properly propagated to the agent with descriptive error messages

## Implementation Details

The MCP integration consists of:

1. **McpClient**: Main client class for connecting to MCP servers
2. **McpTool**: Wrapper that makes MCP tools compatible with Semantic Kernel
3. **McpPlugin**: Plugin wrapper that holds MCP tools
4. **Configuration**: Extended agent config to support MCP server specifications

### Key Classes

- `McpClient`: Manages connections to multiple MCP servers
- `McpServerConfig`: Pydantic model for server configuration
- `McpPlugin`: Semantic Kernel plugin containing MCP tools
- `McpClientManager`: Singleton manager for global client instance

## Dependencies

The MCP integration requires different dependencies based on transport types:

### Base Dependency
```toml
"mcp>=1.0.0"  # Core MCP client with stdio support
```

### Optional Transport Dependencies
```toml
# For WebSocket transport support
"mcp[websocket]>=1.0.0"

# For HTTP transport support  
"mcp[http]>=1.0.0"

# For all transport types
"mcp[websocket,http]>=1.0.0"
```

**Note**: If you try to use a transport without its required dependencies, you'll get a helpful error message with installation instructions.

## Logging

MCP operations are logged at appropriate levels:

- **INFO**: Successful connections, tool discoveries, plugin registrations
- **WARNING**: Missing tools, empty server responses
- **ERROR**: Connection failures, tool invocation errors
- **DEBUG**: Detailed operation traces

## Best Practices

1. **Server naming**: Use descriptive names for your MCP servers
2. **Error tolerance**: Design your prompts to handle cases where tools might be unavailable
3. **Resource management**: MCP connections are managed automatically but consider the resource impact of multiple servers
4. **Security**: Be cautious with filesystem and database access - only configure servers with appropriate permissions
5. **Testing**: Test your MCP server configurations independently before integrating with agents

## Troubleshooting

### Common Issues

#### General Issues
1. **Import errors**: Ensure the `mcp` package is installed
2. **Tool not found**: Verify the MCP server is exposing the expected tools
3. **Configuration validation**: Check required fields for your transport type

#### Stdio Transport Issues
1. **Permission errors**: Check file system permissions for server executables
2. **Command not found**: Verify command is in PATH or use absolute path
3. **Connection failures**: Check command and arguments are correct

#### WebSocket Transport Issues
1. **SSL/TLS errors**: Check certificate validity for `wss://` URLs
2. **Connection timeout**: Verify server is running and accessible
3. **Authentication failures**: Check headers and tokens are correct
4. **Missing dependencies**: Install with `pip install 'mcp[websocket]'`

#### HTTP Transport Issues
1. **404 errors**: Verify base_url is correct and endpoints exist
2. **401/403 errors**: Check API key and authentication headers
3. **Timeout errors**: Increase timeout value or check server response time
4. **Missing dependencies**: Install with `pip install 'mcp[http]'`

### Debugging

Enable detailed logging to troubleshoot MCP integration:

```python
import logging

# Enable MCP client debugging
logging.getLogger('sk_agents.mcp_client').setLevel(logging.DEBUG)

# Enable transport-specific debugging
logging.getLogger('mcp.client').setLevel(logging.DEBUG)
```

### Transport-Specific Debugging

```bash
# Test stdio server manually
npx @modelcontextprotocol/server-filesystem /tmp

# Test WebSocket connection
wscat -c "wss://example.com/mcp" -H "Authorization: Bearer TOKEN"

# Test HTTP endpoint
curl -H "Authorization: Bearer TOKEN" https://api.example.com/v1/health
```

## Future Enhancements

Planned improvements include:

- **Authentication support**: OAuth2 and other auth methods for MCP servers
- **Tool governance**: HITL and authorization integration
- **Performance optimization**: Connection pooling and caching
- **Dynamic discovery**: Runtime tool discovery and registration