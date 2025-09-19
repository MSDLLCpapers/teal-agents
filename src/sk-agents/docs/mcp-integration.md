# MCP Integration for Teal Agents

The Teal Agents platform supports integration with Model Context Protocol (MCP) servers using supported transport protocols, allowing agents to automatically discover and use tools from external MCP servers.

## Overview

The MCP client implementation provides:

- **Automatic tool discovery**: Connect to MCP servers and automatically register their tools
- **Seamless integration**: MCP tools work like native plugins in the Semantic Kernel framework
- **Configuration-driven**: Specify MCP servers in your agent configuration
- **Error handling**: Graceful handling of connection failures and tool invocation errors

## Supported Transports

Teal Agents supports the following MCP SDK transports:

- **stdio**: Local subprocess communication
- **http**: HTTP with Streamable HTTP and SSE fallback (remote servers)

## Planned Transports

- **websocket**: WebSocket connections (when available in the MCP Python SDK)

## Configuration

To use MCP servers with your agent, add the `mcp_servers` configuration to your agent config. Transport is inferred when omitted:

- If `url` is provided (and `command` is not), transport is `http`
- If `command` is provided (and `url` is not), transport is `stdio`
- If both are provided without `transport`, validation will fail (ambiguous)

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
  
  # MCP servers
  mcp_servers:
    # Stdio transport (local subprocess)
    - name: filesystem
      command: npx
      args:
        - "@modelcontextprotocol/server-filesystem"
        - "/path/to/allowed/directory"
      env:
        NODE_ENV: production
    
    # HTTP transport (minimal config)
    - name: user-management
      url: "https://auth.example.com/api/v2/mcp"
      headers:
        Authorization: "Bearer ${USER_MGMT_API_KEY}"

    - name: sqlite
      command: python3
      args:
        - "-m"
        - "mcp_server_sqlite"
        - "--db-path"
        - "/path/to/data.db"
```

## MCP Server Configuration

### Configuration Fields

All MCP servers require:
- **name**: Unique identifier for the server

Transport-specific requirements (transport is inferred if omitted):
- **stdio**: requires **command** (optional: **args**, **env**)
- **http**: requires **url** (optional: **headers**, **timeout**, **sse_read_timeout**)

Authentication fields (optional):
- **auth_server**: OAuth2 authorization server URL for automatic token management
- **scopes**: List of required OAuth2 scopes

Governance fields (optional):
- **tool_governance_overrides**: Manual overrides for specific tool governance settings

Note: The `transport` field is optional. If you provide both `command` and `url`, you must set `transport` to disambiguate.

## Example MCP Servers

### Filesystem Server (Stdio)
```yaml
mcp_servers:
  - name: filesystem
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "/safe/directory"
```

### SQLite Server (Stdio)
```yaml
mcp_servers:
  - name: sqlite
    command: python3
    args:
      - "-m"
      - "mcp_server_sqlite"
      - "--db-path"
      - "/path/to/data.db"
```

### GitHub Server (HTTP with OAuth2)
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
```

### Python MCP Server (Local with Environment)
```yaml
mcp_servers:
  - name: custom-tools
    command: python
    args:
      - "/path/to/my_mcp_server.py"
    env:
      PYTHONPATH: "/opt/mcp-tools"
      DEBUG: "true"
    tool_governance_overrides:
      execute_command:
        requires_hitl: true
        cost: "high"
```

## Authentication & Authorization

### OAuth2 Integration

MCP servers that require authentication can integrate with the platform's OAuth2 infrastructure:

```yaml
mcp_servers:
  - name: github
    url: "https://api.github.com/mcp"
    auth_server: "https://github.com/login/oauth"
    scopes: ["repo", "read:user"]
```

**How it works:**
1. The platform checks if the user has stored OAuth2 tokens for the specified `auth_server` and `scopes`
2. If tokens exist, they're automatically used for MCP server authentication
3. If tokens are missing, an auth challenge is returned to prompt user authentication
4. Once authenticated, tokens are stored and reused for future requests

### Manual Authentication Headers

For servers requiring custom authentication, use the `headers` field:

```yaml
mcp_servers:
  - name: api-server
    url: "https://api.example.com/mcp"
    headers:
      Authorization: "Bearer ${API_TOKEN}"
      X-API-Key: "${API_KEY}"
```

## Tool Governance

### Automatic Governance Mapping

MCP tools automatically inherit governance settings based on their annotations:

- `destructiveHint: true` → `requires_hitl: true, cost: "high"`
- `readOnlyHint: true` → `requires_hitl: false, cost: "low"`
- Default → `requires_hitl: false, cost: "medium"`

### Manual Governance Overrides

Override automatic governance settings for specific tools:

```yaml
mcp_servers:
  - name: github
    url: "https://api.github.com/mcp"
    tool_governance_overrides:
      create_repository:
        requires_hitl: false    # Override auto-inferred HITL requirement
        cost: "medium"          # Override auto-inferred cost level
        data_sensitivity: "proprietary"
      delete_repository:
        requires_hitl: true     # Force HITL approval
        cost: "high"            # High cost operation
        data_sensitivity: "sensitive"
```

**Governance Fields:**
- `requires_hitl`: Whether human approval is required (boolean)
- `cost`: Resource cost level (`"low"`, `"medium"`, `"high"`)
- `data_sensitivity`: Data classification (`"public"`, `"proprietary"`, `"sensitive"`)

## Tool Usage

Once configured, MCP tools are automatically available to your agent. They appear in the kernel with the format `<server_name>_<tool_name>` to avoid naming collisions.

For example, if you have a filesystem server named "filesystem" with a "read_file" tool, it would be registered as `filesystem_read_file`.

**Tool Discovery Process:**
1. Agent connects to MCP servers during initialization
2. Tools are discovered and registered as Semantic Kernel functions
3. Governance metadata is applied (automatic mapping + manual overrides)
4. Tools become available for agent invocation

## Error Handling

The MCP client includes robust error handling:

- **Connection failures**: Transport-specific error messages help identify the issue
- **Authentication failures**: Clear guidance for HTTP authentication problems
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

The MCP integration requires:

```toml
"mcp>=1.0.0"  # Core MCP client with stdio and HTTP/SSE support
```

**Note**: The base `mcp` package includes all currently supported transports.

## Security Features

The implementation includes security enhancements:

1. **Credential Sanitization**: API keys and sensitive arguments are redacted from logs
2. **Input Validation**: Command injection prevention for stdio transport
3. **URL Sanitization**: Sensitive URL parameters are removed from logs
4. **Authentication**: Proper Bearer token support for HTTP transport

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
1. **Import errors**: Ensure the `mcp` package is installed: `pip install mcp`
2. **Tool not found**: Verify the MCP server is exposing the expected tools
3. **Configuration validation**: Check that `command` field is provided

#### Stdio Transport Issues
1. **Permission errors**: Check file system permissions for server executables
2. **Command not found**: Verify command is in PATH or use absolute path
3. **Connection failures**: Check command and arguments are correct
4. **Server startup errors**: Check if the MCP server starts correctly when run manually

### Debugging

Enable detailed logging to troubleshoot MCP integration:

```python
import logging

# Enable MCP client debugging
logging.getLogger('sk_agents.mcp_client').setLevel(logging.DEBUG)

# Enable MCP SDK debugging
logging.getLogger('mcp').setLevel(logging.DEBUG)
```

### Testing MCP Servers

```bash
# Test stdio server manually
npx @modelcontextprotocol/server-filesystem /tmp

# Test Python MCP server
python /path/to/my_mcp_server.py

# Test Node.js MCP server
node /path/to/my_mcp_server.js
```

## Limitations

### Currently Not Supported

- **WebSocket transport**: Not yet available in the MCP Python SDK
- **Custom transport protocols**: Only stdio and http are supported

