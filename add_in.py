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



class AgentConfig(BaseModel):
    # Existing fields...
    mcp_servers: list[McpServerConfig] | None = None



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
      auth_server: "https://api.example.com/oauth2"
      scopes: ["api.read", "api.write"]
      timeout: 30.0                 # Optional: connection timeout (seconds)
      sse_read_timeout: 300.0       # Optional: SSE read timeout (seconds)
      headers:                      # Optional: Non-sensitive HTTP headers
        User-Agent: "TealAgents-MCP/1.1"
        X-Client-Version: "1.0"

### Core Implementation
- ✅ McpClient class with multi-transport connection management
- ✅ McpTool wrapper for Semantic Kernel compatibility  
- ✅ McpPlugin container for tool registration
- ✅ McpServerConfig configuration model with HTTP transport support
- ✅ Transport factory pattern with HTTP transport selection
- ✅ Stdio and HTTP transport implementations (Streamable HTTP + SSE)
- ✅ KernelBuilder integration for MCP loading
- ✅ AgentBuilder updates to pass MCP configuration




class McpTool:
    """Wrapper for MCP tools to make them compatible with Semantic Kernel."""
    
    def __init__(self, name: str, description: str, input_schema: Dict[str, Any], client_session):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.client_session = client_session
        self.original_name = name
        
    async def invoke(self, **kwargs) -> str:
        """Invoke the MCP tool with the provided arguments."""
        try:
            # Basic input validation if schema is available
            if self.input_schema:
                self._validate_inputs(kwargs)
                
            result = await self.client_session.call_tool(self.name, kwargs)
            
            # Handle different result types from MCP
            if hasattr(result, 'content'):
                if isinstance(result.content, list) and len(result.content) > 0:
                    return str(result.content[0].text) if hasattr(result.content[0], 'text') else str(result.content[0])
                return str(result.content)
            elif hasattr(result, 'text'):
                return result.text
            else:
                return str(result)
        except Exception as e:
            logger.error(f"Error invoking MCP tool {self.name}: {e}")
            
            # Provide helpful error messages
            error_msg = str(e).lower()
            if 'timeout' in error_msg:
                raise RuntimeError(f"MCP tool '{self.name}' timed out. Check server responsiveness.") from e
            elif 'connection' in error_msg:
                raise RuntimeError(f"MCP tool '{self.name}' connection failed. Check server availability.") from e
            else:
                raise RuntimeError(f"MCP tool '{self.name}' failed: {e}") from e
            
    def _validate_inputs(self, kwargs: Dict[str, Any]) -> None:
        """Basic input validation against the tool's JSON schema."""
        if not isinstance(self.input_schema, dict):
            return
            
        properties = self.input_schema.get('properties', {})
        required = self.input_schema.get('required', [])
        
        # Check required parameters
        for req_param in required:
            if req_param not in kwargs:
                raise ValueError(f"Missing required parameter '{req_param}' for tool '{self.name}'")
        
        # Warn about unexpected parameters
        for param in kwargs:
            if param not in properties:
                logger.warning(f"Unexpected parameter '{param}' for tool '{self.name}'")


class McpPlugin(BasePlugin):
    """Plugin wrapper that holds MCP tools for Semantic Kernel integration."""
    
    def __init__(self, tools: List[McpTool], server_name: str = None, authorization: str | None = None, extra_data_collector=None):
        super().__init__(authorization, extra_data_collector)
        self.tools = tools
        self.server_name = server_name
        
        # Dynamically add kernel functions for each tool
        for tool in tools:
            self._add_tool_function(tool)
    
    def _add_tool_function(self, tool: McpTool):
        """Add a tool as a kernel function to this plugin."""
        
        # Create a closure that captures the specific tool instance
        def create_tool_function(captured_tool: McpTool):
            # Create unique tool name to avoid collisions
            unique_name = f"{self.server_name}_{captured_tool.name}" if self.server_name else captured_tool.name
            
            @kernel_function(
                name=unique_name,
                description=f"[{self.server_name or 'MCP'}] {captured_tool.description}",
            )
            async def tool_function(**kwargs):
                return await captured_tool.invoke(**kwargs)
            return tool_function
        
        # Create the function and set as attribute
        tool_function = create_tool_function(tool)
        
        # Sanitize tool name for Python attribute
        base_name = f"{self.server_name}_{tool.name}" if self.server_name else tool.name
        attr_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in base_name)
        if not attr_name[0].isalpha() and attr_name[0] != '_':
            attr_name = f'tool_{attr_name}'
            
        setattr(self, attr_name, tool_function)


class McpClient:
    """
    Multi-server MCP client manager with Semantic Kernel integration.
    
    This class manages connections to multiple MCP servers and provides
    seamless integration with the Semantic Kernel framework. It uses the
    MCP Python SDK for actual transport handling.
    
    Currently supported:
    - stdio: Local subprocess communication
    
    Future transports will be added as they become available in the MCP SDK.
    """
    
    def __init__(self):
        """Initialize the MCP client."""
        self.connected_servers: Dict[str, Any] = {}
        self.server_configs: Dict[str, McpServerConfig] = {}
        self.plugins: Dict[str, McpPlugin] = {}
        self._connection_stacks: Dict[str, AsyncExitStack] = {}
        self._connection_health: Dict[str, bool] = {}
        
    async def connect_server(self, server_config: McpServerConfig) -> None:
        """
        Connect to an MCP server and register its tools.
        
        Args:
            server_config: Configuration for the MCP server to connect to
            
        Raises:
            ConnectionError: If connection to the MCP server fails
            ValueError: If server configuration is invalid
        """
        # Clean up any existing connection first
        await self.disconnect_server(server_config.name)
        
        connection_stack = AsyncExitStack()
        try:
            # Get transport info for logging
            transport_info = get_transport_info(server_config)
            logger.info(f"Connecting to MCP server '{server_config.name}' via {transport_info}")
            
            # Create session using MCP SDK
            session = await create_mcp_session(server_config, connection_stack)
            
            # Initialize the session
            await session.initialize()
            
            # Store the session and resources
            self.connected_servers[server_config.name] = session
            self.server_configs[server_config.name] = server_config
            self._connection_stacks[server_config.name] = connection_stack
            self._connection_health[server_config.name] = True
            
            # Discover and register tools
            await self._discover_and_register_tools(server_config.name, session)
            
            logger.info(f"Successfully connected to MCP server: {server_config.name}")
            
        except Exception as e:
            # Cleanup on failure
            await connection_stack.aclose()
            logger.error(f"Failed to connect to MCP server '{server_config.name}': {e}")
            
            # Provide transport-specific error guidance
            error_msg = str(e).lower()
            
            if server_config.transport == "stdio":
                # Stdio-specific errors
                if 'permission' in error_msg or 'access' in error_msg:
                    raise ConnectionError(
                        f"Permission denied for MCP server '{server_config.name}'. "
                        f"Check executable permissions for: {server_config.command}"
                    ) from e
                elif 'not found' in error_msg or 'no such file' in error_msg:
                    raise ConnectionError(
                        f"Command not found for MCP server '{server_config.name}'. "
                        f"Verify command is in PATH or use absolute path: {server_config.command}"
                    ) from e
            elif server_config.transport == "http":
                # HTTP-specific errors
                if 'timeout' in error_msg or 'timed out' in error_msg:
                    raise ConnectionError(
                        f"Timeout connecting to MCP server '{server_config.name}' at {server_config.url}. "
                        f"Check server availability and network connectivity."
                    ) from e
                elif 'connection' in error_msg or 'unreachable' in error_msg:
                    raise ConnectionError(
                        f"Cannot reach MCP server '{server_config.name}' at {server_config.url}. "
                        f"Verify the URL is correct and the server is running."
                    ) from e
                elif '401' in error_msg or 'unauthorized' in error_msg:
                    raise ConnectionError(
                        f"Authentication failed for MCP server '{server_config.name}'. "
                        f"Check your credentials and authorization headers."
                    ) from e
                elif '404' in error_msg or 'not found' in error_msg:
                    raise ConnectionError(
                        f"MCP server endpoint not found: {server_config.url}. "
                        f"Verify the URL path is correct (typically ends with /sse or /mcp)."
                    ) from e
                elif '503' in error_msg or 'unavailable' in error_msg:
                    raise ConnectionError(
                        f"MCP server '{server_config.name}' is temporarily unavailable. "
                        f"Try again later or contact the server administrator."
                    ) from e
                
            # Generic fallback error
            raise ConnectionError(f"Could not connect to MCP server '{server_config.name}': {e}") from e
    
    async def _discover_and_register_tools(self, server_name: str, session) -> None:
        """Discover tools from the connected MCP server and create plugin wrappers."""
        try:
            # List available tools from the server
            tools_result = await session.list_tools()
            
            if not tools_result or not hasattr(tools_result, 'tools'):
                logger.warning(f"No tools found on MCP server: {server_name}")
                return
            
            # Create MCP tool wrappers
            mcp_tools = []
            for tool_info in tools_result.tools:
                mcp_tool = McpTool(
                    name=tool_info.name,
                    description=tool_info.description or f"Tool {tool_info.name} from {server_name}",
                    input_schema=getattr(tool_info, 'inputSchema', {}) or {},
                    client_session=session
                )
                mcp_tools.append(mcp_tool)
                
                logger.info(f"Discovered tool: {tool_info.name} from server {server_name}")
            
            # Create a plugin for this server's tools
            if mcp_tools:
                plugin = McpPlugin(mcp_tools, server_name=server_name)
                self.plugins[server_name] = plugin
                logger.info(f"Created plugin for server {server_name} with {len(mcp_tools)} tools")
            
        except Exception as e:
            logger.error(f"Failed to discover tools from MCP server {server_name}: {e}")
            raise
    
    def get_plugin(self, server_name: str) -> Optional[McpPlugin]:
        """Get the plugin for a specific MCP server."""
        return self.plugins.get(server_name)
    
    def get_all_plugins(self) -> Dict[str, McpPlugin]:
        """Get all registered MCP plugins."""
        return self.plugins.copy()
    
    def register_plugins_with_kernel(self, kernel: Kernel) -> None:
        """Register all MCP plugins with a Semantic Kernel instance."""
        for server_name, plugin in self.plugins.items():
            try:
                kernel.add_plugin(plugin, f"mcp_{server_name}")
                logger.info(f"Registered MCP plugin for server {server_name} with kernel")
            except Exception as e:
                logger.error(f"Failed to register MCP plugin for server {server_name}: {e}")
                raise
    
    async def disconnect_server(self, server_name: str) -> None:
        """Disconnect from an MCP server and clean up resources."""
        try:
            # Clean up connection resources
            if server_name in self._connection_stacks:
                connection_stack = self._connection_stacks[server_name]
                await connection_stack.aclose()
                del self._connection_stacks[server_name]
                
            # Clean up tracking dictionaries
            for dictionary in [
                self.connected_servers,
                self.server_configs, 
                self.plugins,
                self._connection_health
            ]:
                if server_name in dictionary:
                    del dictionary[server_name]
                    
            logger.info(f"Disconnected from MCP server: {server_name}")
            
        except Exception as e:
            logger.error(f"Error disconnecting from MCP server {server_name}: {e}")
    
    async def disconnect_all(self) -> None:
        """Disconnect from all connected MCP servers."""
        server_names = list(self.connected_servers.keys())
        disconnect_tasks = [self.disconnect_server(name) for name in server_names]
        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)
    
    def is_connected(self, server_name: str) -> bool:
        """Check if connected to a specific MCP server."""
        return (
            server_name in self.connected_servers and 
            server_name in self._connection_health and
            self._connection_health[server_name]
        )
        
    def mark_connection_unhealthy(self, server_name: str) -> None:
        """Mark a connection as unhealthy."""
        if server_name in self._connection_health:
            self._connection_health[server_name] = False
            logger.warning(f"Marked MCP server {server_name} as unhealthy")
    
    def get_connected_servers(self) -> List[str]:
        """Get list of connected MCP server names."""
        return list(self.connected_servers.keys())


class McpClientManager:
    """Thread-safe singleton manager for MCP client instances."""
    
    _instance: Optional['McpClientManager'] = None
    _client: Optional[McpClient] = None
    _lock: Optional[asyncio.Lock] = None
    _thread_lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_client(self) -> McpClient:
        """Get or create the global MCP client instance (thread-safe)."""
        if self._client is None:
            # Initialize async lock if needed
            if self._lock is None:
                with self._thread_lock:
                    if self._lock is None:
                        self._lock = asyncio.Lock()
                        
            async with self._lock:
                # Double-check after acquiring lock
                if self._client is None:
                    self._client = McpClient()
        return self._client
    
    async def reset_client(self) -> None:
        """Reset the global MCP client instance (thread-safe)."""
        if self._lock is None:
            with self._thread_lock:
                if self._lock is None:
                    self._lock = asyncio.Lock()
                    
        async with self._lock:
            if self._client is not None:
                await self._client.disconnect_all()
                self._client = None


def get_mcp_client() -> McpClient:
    """Get the global MCP client instance."""
    manager = McpClientManager()
    
    # Try to get existing client first (fast path)
    if manager._client is not None:
        return manager._client
    
    # Need to create client - handle async context properly
    try:
        asyncio.get_running_loop()
        # We're in an async context but called sync function
        logger.warning(
            "get_mcp_client() called from async context. "
            "Consider using 'await McpClientManager().get_client()' instead."
        )
        # Create client synchronously for backward compatibility
        if manager._client is None:
            manager._client = McpClient()
        return manager._client
    except RuntimeError:
        # No event loop, safe to use asyncio.run()
        return asyncio.run(manager.get_client())
