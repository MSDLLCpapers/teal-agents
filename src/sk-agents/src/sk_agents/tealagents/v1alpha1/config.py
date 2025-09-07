from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    headers: Optional[Dict[str, str]] = None
    timeout: Optional[float] = 30.0
    sse_read_timeout: Optional[float] = 300.0
    
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
        
        return self


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    model: str
    system_prompt: str
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    plugins: list[str] | None = None
    remote_plugins: list[str] | None = None
    mcp_servers: list[McpServerConfig] | None = None
