# MCP Integration for Teal Agents

The Teal Agents platform now supports integration with Model Context Protocol (MCP) servers, allowing agents to automatically discover and use tools from external MCP servers.

## Overview

The MCP client implementation provides:

- **Automatic tool discovery**: Connect to MCP servers and automatically register their tools
- **Seamless integration**: MCP tools work like native plugins in the Semantic Kernel framework
- **Configuration-driven**: Specify MCP servers in your agent configuration
- **Error handling**: Graceful handling of connection failures and tool invocation errors

## Configuration

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
  
  # MCP servers
  mcp_servers:
    - name: filesystem
      command: npx
      args:
        - "@modelcontextprotocol/server-filesystem"
        - "/path/to/allowed/directory"
      env:
        NODE_ENV: production
    
    - name: sqlite
      command: python
      args:
        - "-m"
        - "mcp_server_sqlite"
        - "--db-path"
        - "/path/to/database.db"
```

## MCP Server Configuration

Each MCP server requires:

- **name**: Unique identifier for the server
- **command**: Command to start the MCP server
- **args**: Command line arguments (optional)
- **env**: Environment variables (optional)

## Example MCP Servers

### Filesystem Server
```yaml
mcp_servers:
  - name: filesystem
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "/safe/directory"
```

### SQLite Server
```yaml
mcp_servers:
  - name: sqlite
    command: python
    args:
      - "-m"
      - "mcp_server_sqlite"
      - "--db-path"
      - "/path/to/data.db"
```

### Git Server
```yaml
mcp_servers:
  - name: git
    command: npx
    args:
      - "@modelcontextprotocol/server-git"
      - "--repository"
      - "/path/to/repo"
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

The MCP integration adds the following dependency:

```toml
"mcp>=1.0.0"
```

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

1. **Import errors**: Ensure the `mcp` package is installed
2. **Connection failures**: Verify MCP server commands and arguments
3. **Permission errors**: Check file system permissions for server executables
4. **Tool not found**: Verify the MCP server is exposing the expected tools

### Debugging

Enable detailed logging to troubleshoot MCP integration:

```python
import logging
logging.getLogger('sk_agents.mcp_client').setLevel(logging.DEBUG)
```

## Future Enhancements

Planned improvements include:

- **Authentication support**: OAuth2 and other auth methods for MCP servers
- **Tool governance**: HITL and authorization integration
- **Performance optimization**: Connection pooling and caching
- **Dynamic discovery**: Runtime tool discovery and registration