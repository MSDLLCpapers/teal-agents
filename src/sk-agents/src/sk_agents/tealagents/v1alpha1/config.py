from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class McpServerConfig(BaseModel):
    """Configuration for an MCP server connection - only supported transports."""
    model_config = ConfigDict(extra="allow")
    
    name: str
    # Only stdio transport is currently supported by MCP Python SDK
    transport: Literal["stdio"] = "stdio"
    
    # Stdio transport fields
    command: Optional[str] = None
    args: List[str] = []
    env: Optional[Dict[str, str]] = None
    
    @model_validator(mode='after')
    def validate_transport_fields(self):
        """Validate that required fields are provided for stdio transport."""
        if not self.command:
            raise ValueError("'command' is required for stdio transport")
        # Basic security validation
        if any(char in (self.command or "") for char in [';', '&', '|', '`', '$']):
            raise ValueError("Command contains potentially unsafe characters")
        
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
