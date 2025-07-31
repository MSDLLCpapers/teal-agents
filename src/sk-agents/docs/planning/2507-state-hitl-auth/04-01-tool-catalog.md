# Phase 4 - Plugin Catalog
In this phase, we will introduce the concept of a plugin catalog.

## Overview
While we have not yet landed on the technology to use, we will need to continue forward
with the design and integration of the concept of a plugin catalog to allow us to move
forward with HITL and authorization. The plugin catalog will be the centralized repository
for tools made available to agents, and will provide a set of metadata for each tool
that can be used to determine things like which authorization server and scopes are
required for a particular tool invocation and whether a specific tool requires HITL
confirmation prior to execution.

Since no decision has been reached on an actual implementation technology, we will
proceed with establishing an abstraction layer which, for the time being, will require
manual configuration of available tools.

## Abstraction Layer Design
The Plugin concept can be represented as the following:

```python
class PluginType(BaseModel):
    type_name: Literal["code", "mcp"]

class Governance(BaseModel):
    requires_hitl: bool
    cost: Literal["low", "medium", "high"]
    data_sensitivity: Literal["public", "proprietary", "confidential", "sensitive"]

class PluginAuth(BaseModel):
    auth_type: Literal["oauth2"]

class Oauth2PluginAuth(PluginAuth):
    auth_server: str
    scopes: List[str]

class PluginTool(BaseModel):
    tool_id: str
    name: str
    description: str
    governance: Governance

class Plugin(BaseModel):
    plugin_id: str
    name: str
    description: str
    version: str
    owner: str
    plugin_type: Type[PluginType]
    auth: Type[PluginAuth] | None
    tools: List[PluginTool]
```

`PluginType` will be a base class for the different types of plugins available.
Currently, the only two should be `code` (which refers to a python code plugin) and
`mcp` (which refers to a Streamable HTTP MCP Server). Individual plugin types should
have subclasses that provide additional metadata for that specific plugin type, when
applicable. I'm thinking that, currently, `code` type plugins won't require additional
metadata, but `mcp` will, though I'm not sure what it will be yet.

Plugin auth will be applied at the plugin level and will be applicable for all tools in
a given plugin (is this the right approach?). Governance will be applied to individual
tools within a plugin.  I believe the other objects and fields are self-explanatory.

The Plugin catalog will need to provide a method which allows the retrieval of the
information about the plugin for a given plugin or tool ID. I'm not sure what the most
appropriate lookup method will be, so for the time being let's accommodate both.

The Plugin catalog should be implemented as an abstract class.

We should define a single, initial implementation called `LocalPluginCatalog` which will
simply read a JSON file from the local filesystem which contains the defined plugins.

The application should rely on two new environment variables:
`TA_PLUGIN_CATALOG_MODULE` - The path and file name of the module which will implement
the desired plugin catalog provider class.
`TA_PLUGIN_CATALOG_CLASS` - The name of the class within the module which implements the
plugin catalog.

Additionally, the initial `LocalPluginCatalog` implementation should leverage an
additional environment variable `TA_PLUGIN_CATALOG_FILE` which will be the path to the
JSON file containing the plugin definitions.

Finally, we should additionally define a Plugin catalog factory which will be
responsible for instantiating the plugin catalog based on the environment variables.

This should use a Singleton pattern. Note, there's an existing `Singleton` class in the
`ska-utils` package which can be used for this.

Re-review @planning/2507-state-hitl-auth/04-03-hitl-implementation-plan.md to see where
this catalog should be hooked in and include appropriate tasks to achieve that.
