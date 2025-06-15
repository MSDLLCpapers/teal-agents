# MCP-Enabled Teal Agents Examples

This directory contains example configurations for Teal Agents that integrate with Model Context Protocol (MCP) servers, demonstrating how to extend agent capabilities with external tools and data sources.

## Overview

The MCP integration allows Teal Agents to:
- Connect to external data sources (filesystems, databases, APIs)
- Use specialized tools and services
- Access real-time information and dynamic resources
- Extend capabilities beyond built-in plugins

## Example Agents

### 1. MCP Filesystem Agent (`mcp-filesystem-agent/`)

**Purpose**: Demonstrates basic file operations using MCP filesystem server.

**Capabilities**:
- Read and write files
- Create and manage directories
- Search file contents
- File organization and management

**MCP Server**: `@modelcontextprotocol/server-filesystem`

**Usage**:
```bash
cd /home/agp/teal-agents/src/sk-agents
export TA_SERVICE_CONFIG="examples/mcp-filesystem-agent/config.yaml"
export TA_AGENT_NAME="filesystem_agent"
uv run -- fastapi run src/sk_agents/app.py
```

### 2. MCP Multi-Server Agent (`mcp-multi-server-agent/`)

**Purpose**: Shows integration with multiple MCP servers in a sequential workflow.

**Capabilities**:
- Data collection from multiple sources
- SQLite database operations
- Web search integration
- Comprehensive data analysis pipeline

**MCP Servers**:
- Filesystem server for data files
- SQLite server for structured data
- Web search server for external information

**Usage**:
```bash
export TA_SERVICE_CONFIG="examples/mcp-multi-server-agent/config.yaml"
export TA_AGENT_NAME="data_analyst"
export BRAVE_API_KEY="your_brave_api_key"  # Optional for web search
uv run -- fastapi run src/sk_agents/app.py
```

### 3. MCP Pharmaceutical Agent (`mcp-pharmaceutical-agent/`)

**Purpose**: Specialized agent for pharmaceutical research with domain-specific MCP integrations.

**Capabilities**:
- Molecular structure analysis
- Compound database queries
- ADMET property evaluation
- Research data management
- Literature and patent analysis

**MCP Servers**:
- Filesystem for research workspace
- SQLite for compound databases
- Web API for PubChem integration

**Usage**:
```bash
export TA_SERVICE_CONFIG="examples/mcp-pharmaceutical-agent/config.yaml"
export TA_AGENT_NAME="pharma_researcher"
uv run -- fastapi run src/sk_agents/app.py
```

## MCP Configuration Format

In your agent configuration YAML, add MCP servers to the agent specification:

```yaml
spec:
  agents:
    - name: my_agent
      model: gpt-4o-mini
      system_prompt: "Your agent instructions..."
      mcp_servers:
        - name: server_identifier
          command: command_to_start_server
          args: ["arg1", "arg2"]
          env:
            ENV_VAR: "value"
          timeout: 30
```

### MCP Server Configuration Options

- **name**: Unique identifier for the MCP server
- **command**: Command to start the MCP server process
- **args**: List of command-line arguments
- **env**: Environment variables (supports `${VAR}` substitution)
- **timeout**: Connection timeout in seconds (default: 30)

## Available MCP Tools

Once MCP servers are configured, agents gain access to these Semantic Kernel functions:

### Core MCP Functions

1. **`mcp-list_mcp_tools`**: List all available tools from connected MCP servers
2. **`mcp-call_mcp_tool`**: Execute a specific tool with parameters
3. **`mcp-read_mcp_resource`**: Read resources (files, database records, etc.)
4. **`mcp-get_mcp_prompt`**: Get prompt templates from MCP servers

### Usage in Agent Conversations

Agents automatically discover and use MCP tools. You can also explicitly reference them:

```
User: "List the files in the current directory"
Agent: I'll use the MCP filesystem tools to list the files for you.
[Agent calls mcp-call_mcp_tool with filesystem server]
```

## Setting Up MCP Servers

### Prerequisites

Install the MCP servers you want to use:

```bash
# Filesystem server
npm install -g @modelcontextprotocol/server-filesystem

# SQLite server
pip install mcp-server-sqlite

# Additional servers as needed
```

### Environment Variables

Set up required environment variables:

```bash
# For workspace paths
export WORKSPACE_PATH="/path/to/workspace"

# For API keys (if using web services)
export BRAVE_API_KEY="your_api_key"
export OPENAI_API_KEY="your_openai_key"

# For database paths
export DB_PATH="/path/to/database.db"
```

## Development Guidelines

### Creating New MCP-Enabled Agents

1. **Define the agent's purpose** and required MCP capabilities
2. **Choose appropriate MCP servers** for the needed functionality
3. **Configure the agent YAML** with MCP server specifications
4. **Write clear system prompts** that explain available MCP tools
5. **Test the integration** with various MCP operations

### Best Practices

1. **Error Handling**: MCP operations can fail; ensure agents handle errors gracefully
2. **Security**: Validate file paths and database queries to prevent security issues
3. **Performance**: Consider timeout values and connection limits
4. **Documentation**: Clearly document which MCP servers are required

### Troubleshooting

**Common Issues**:

1. **MCP Server Not Starting**: Check that the server command and arguments are correct
2. **Connection Timeouts**: Increase timeout values or check server responsiveness
3. **Environment Variables**: Ensure required environment variables are set
4. **Permissions**: Verify file and directory permissions for filesystem operations

**Debugging**:

- Check agent logs for MCP connection errors
- Test MCP servers independently before integration
- Use the `list_mcp_tools` function to verify server connectivity

## Advanced Usage

### Custom MCP Server Integration

You can create custom MCP servers for specialized functionality:

```python
# custom_mcp_server.py
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("CustomServer")

@mcp.tool()
def custom_analysis(data: str) -> str:
    # Your custom logic here
    return f"Analysis result: {data}"

if __name__ == "__main__":
    mcp.run()
```

Then reference it in your agent configuration:

```yaml
mcp_servers:
  - name: custom
    command: python
    args: ["custom_mcp_server.py"]
```

### Dynamic MCP Configuration

For dynamic environments, you can use environment variable substitution:

```yaml
mcp_servers:
  - name: dynamic_db
    command: python
    args: ["-m", "mcp_server_sqlite", "${DATABASE_PATH}"]
    env:
      DB_TIMEOUT: "${DB_TIMEOUT:-30}"
```

## Contributing

When creating new MCP-enabled agent examples:

1. Follow the existing directory structure
2. Include comprehensive documentation
3. Test with multiple MCP server combinations
4. Provide clear setup instructions
5. Include error handling examples

For questions or issues, please refer to the main Teal Agents documentation or create an issue in the repository.