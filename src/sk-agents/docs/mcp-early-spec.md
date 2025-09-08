src/sk_agents/
├── mcp_client.py                           # Main MCP client implementation
├── tealagents/v1alpha1/
│   ├── config.py                          # Extended with McpServerConfig
│   ├── agent_builder.py                   # Updated to pass MCP config
│   └── kernel_builder.py                  # Extended with MCP loading
└── pyproject.toml     

```python
class McpServerConfig(BaseModel):
    """Configuration for an MCP server connection supporting multiple transports."""
    model_config = ConfigDict(extra="allow")
    
    # Universal fields
    name: str                                    # Unique server identifier
    transport: Literal["stdio", "http"] = "stdio"  # Transport protocol
    
    # Stdio transport fields
    command: Optional[str] = None               # Command to start server
    args: List[str] = []                       # Command arguments  
    env: Optional[Dict[str, str]] = None       # Environment variables
    
    # HTTP transport fields (supports both Streamable HTTP and SSE)
    url: Optional[str] = None                  # HTTP/SSE endpoint URL
    headers: Optional[Dict[str, str]] = None   # HTTP headers (for auth, etc.)
    timeout: Optional[float] = 30.0            # Connection timeout in seconds
    sse_read_timeout: Optional[float] = 300.0  # SSE read timeout in seconds
```

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

```python
class McpTool:
    """Wrapper for MCP tools to make them compatible with Semantic Kernel."""
    
    name: str                              # Tool name
    description: str                       # Tool description
    input_schema: Dict[str, Any]           # JSON schema for inputs
    client_session: ClientSession          # MCP session reference
    
    async def invoke(self, **kwargs) -> str
```

```python
class McpPlugin(BasePlugin):
    """Plugin wrapper that holds MCP tools for Semantic Kernel integration."""
    
    tools: List[McpTool]
    
    def _add_tool_function(self, tool: McpTool)  # Dynamically adds @kernel_function
```

```python
class AgentConfig(BaseModel):
    # Existing fields...
    mcp_servers: list[McpServerConfig] | None = None
```


### example mcp part config
mcp_servers:
    # Stdio transport (local servers)
    - name: local-server
    transport: stdio               # Optional, defaults to stdio
    command: executable-path       # Required for stdio
    args: ["arg1", "arg2"]        # Optional: command arguments
    env:                          # Optional: environment variables
        VAR_NAME: "value"
        
    # HTTP transport (remote servers)
    - name: http-server
    transport: http
    url: "https://api.example.com/mcp"      # Required: HTTP/SSE endpoint URL
    timeout: 30.0                 # Optional: connection timeout (seconds)
    sse_read_timeout: 300.0       # Optional: SSE read timeout (seconds)
    headers:                      # Optional: HTTP headers for auth/config
        Authorization: "Bearer ${API_KEY}"
        User-Agent: "TealAgents-MCP/1.1"
        X-Client-Version: "1.0"


### Core Implementation
- ✅ McpClient class with multi-transport connection management
- ✅ McpTool and McpPlugin wrapper for tool registration with Semantic Kernel compatibility  
- ✅ McpServerConfig configuration model with stdio and HTTP transport support
- ✅ Transport factory pattern with stdio and HTTP transport selection
- ✅ KernelBuilder integration for MCP loading
- ✅ AgentBuilder updates to pass MCP configuration
