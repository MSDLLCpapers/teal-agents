from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class McpServerConfig(BaseModel):
    """Configuration for an MCP server connection supporting multiple transports."""
    model_config = ConfigDict(extra="allow")
    
    name: str
    transport: Literal["stdio", "websocket", "http"] = "stdio"
    
    # Stdio transport fields
    command: Optional[str] = None
    args: List[str] = []
    env: Optional[Dict[str, str]] = None
    
    # WebSocket transport fields
    url: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    
    # HTTP transport fields  
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    timeout: Optional[int] = 30
    
    @model_validator(mode='after')
    def validate_transport_fields(self):
        """Validate that required fields are provided for each transport type."""
        if self.transport == "stdio":
            if not self.command:
                raise ValueError("'command' is required for stdio transport")
        elif self.transport == "websocket":
            if not self.url:
                raise ValueError("'url' is required for websocket transport")
            if self.url and not (self.url.startswith('ws://') or self.url.startswith('wss://')):
                raise ValueError("WebSocket URL must start with 'ws://' or 'wss://'")
        elif self.transport == "http":
            if not self.base_url:
                raise ValueError("'base_url' is required for http transport")
            if self.base_url and not (self.base_url.startswith('http://') or self.base_url.startswith('https://')):
                raise ValueError("HTTP base_url must start with 'http://' or 'https://'")
        
        return self
    
    @field_validator('timeout')
    @classmethod
    def validate_timeout(cls, v):
        """Validate timeout is positive."""
        if v is not None and v <= 0:
            raise ValueError("timeout must be positive")
        return v


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    model: str
    system_prompt: str
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    plugins: list[str] | None = None
    remote_plugins: list[str] | None = None
    mcp_servers: list[McpServerConfig] | None = None
