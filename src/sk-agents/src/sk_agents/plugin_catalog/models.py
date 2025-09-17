from typing import Literal

from pydantic import BaseModel, Field


# PluginType Models
class CodePluginType(BaseModel):
    type_name: Literal["code"] = "code"


class McpPluginType(BaseModel):
    type_name: Literal["mcp"] = "mcp"
    # Future metadata for MCP plugins will go here


PluginType = CodePluginType | McpPluginType


# Governance Model
class Governance(BaseModel):
    requires_hitl: bool = False
    cost: Literal["low", "medium", "high"]
    data_sensitivity: Literal["public", "proprietary", "confidential", "sensitive"]


# Governance Override Model for MCP tool configuration
class GovernanceOverride(BaseModel):
    """Optional governance overrides for MCP tools. Only specified fields will override auto-inferred values."""
    requires_hitl: bool | None = None
    cost: Literal["low", "medium", "high"] | None = None
    data_sensitivity: Literal["public", "proprietary", "confidential", "sensitive"] | None = None


# PluginAuth Models
class Oauth2PluginAuth(BaseModel):
    auth_type: Literal["oauth2"] = "oauth2"
    auth_server: str
    scopes: list[str]


PluginAuth = Oauth2PluginAuth


# Core Plugin Models
class PluginTool(BaseModel):
    tool_id: str  # Unique identifier, e.g., "Shell-execute"
    name: str
    description: str
    governance: Governance
    auth: PluginAuth | None = Field(None, discriminator="auth_type")


class Plugin(BaseModel):
    plugin_id: str  # e.g., "Shell"
    name: str
    description: str
    version: str
    owner: str
    plugin_type: PluginType = Field(..., discriminator="type_name")
    tools: list[PluginTool]


class PluginCatalogDefinition(BaseModel):
    plugins: list[Plugin]
