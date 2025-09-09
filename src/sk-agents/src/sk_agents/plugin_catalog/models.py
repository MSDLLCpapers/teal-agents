from typing import List, Literal, Union
from pydantic import BaseModel, Field


# PluginType Models
class CodePluginType(BaseModel):
    type_name: Literal["code"] = "code"


class McpPluginType(BaseModel):
    type_name: Literal["mcp"] = "mcp"
    # Future metadata for MCP plugins will go here


PluginType = Union[CodePluginType, McpPluginType]


# Governance Model
class Governance(BaseModel):
    requires_hitl: bool = False
    cost: Literal["low", "medium", "high"]
    data_sensitivity: Literal[
        "public",
        "proprietary",
        "confidential",
        "sensitive"
    ]


# PluginAuth Models
class Oauth2PluginAuth(BaseModel):
    auth_type: Literal["oauth2"] = "oauth2"
    auth_server: str
    scopes: List[str]


PluginAuth = Union[Oauth2PluginAuth]


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
    tools: List[PluginTool]


class PluginCatalogDefinition(BaseModel):
    plugins: List[Plugin]