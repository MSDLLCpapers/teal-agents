# MCP Component Refactoring - Implementation Summary

## Overview
Successfully refactored MCP integration to mirror non-MCP plugin architecture while maintaining stateless execution. MCP plugin classes are now "materialized" at session start (similar to how non-MCP code exists in the codebase), then instantiated at agent build following the exact same pattern.

## Architecture Changes

### Before (Old Architecture)
```
Agent Build (Per Request):
  ├── Connect to MCP servers
  ├── Discover tools
  ├── Create plugin instances
  └── Register with kernel

Issues:
- ❌ Mixed discovery with instantiation
- ❌ Stored active sessions in tools
- ❌ No type annotations for LLM
- ❌ Tool ID format inconsistencies
```

### After (New Architecture)
```
Session Start (Once):
  ├── Discover MCP tools (temp connections)
  ├── Register in catalog (governance/HITL)
  ├── Create McpPlugin CLASSES
  └── Close connections ✅

Agent Build (Per Request):
  ├── Load MCP plugin CLASS from registry
  ├── Instantiate plugin
  └── Register with kernel ✅ SAME as non-MCP!

Tool Invocation:
  ├── HITL check (catalog lookup)
  ├── Create temp connection
  ├── Execute tool
  └── Close connection ✅
```

## Files Modified/Created

### New Files
1. **`src/sk-agents/src/sk_agents/mcp_plugin_registry.py`**
   - `McpPluginRegistry` class for storing materialized plugin classes
   - `discover_and_materialize()` - Discovery at session start
   - `get_plugin_class()` - Retrieve class for instantiation
   - Catalog registration for governance/HITL

### Modified Files

1. **`src/sk-agents/src/sk_agents/mcp_client.py`**
   - `McpTool` class now stateless:
     - Stores `server_config` instead of `client_session`
     - `invoke()` creates temp connection per call
   - `McpPlugin` enhanced:
     - `_build_annotations()` converts JSON schema → Python types
     - `_json_type_to_python()` for type mapping
     - Functions have proper type hints for SK introspection

2. **`src/sk-agents/src/sk_agents/tealagents/kernel_builder.py`**
   - `load_mcp_plugins()` now:
     - Gets plugin CLASS from registry (not creates connections)
     - Instantiates plugin (same as non-MCP)
     - Registers with kernel (same as non-MCP)

3. **`src/sk-agents/src/sk_agents/tealagents/v1alpha1/agent/handler.py`**
   - Added `_ensure_mcp_discovery()` method
   - Called once at first request (class-level initialization)
   - Added to both `invoke()` and `invoke_stream()`

## Key Implementation Details

### 1. Stateless McpTool
```python
class McpTool:
    def __init__(
        self,
        tool_name: str,
        input_schema: Dict[str, Any],
        server_config: McpServerConfig,  # Store config, not session!
        user_id: str
    ):
        self.server_config = server_config  # For lazy connection

    async def invoke(self, **kwargs):
        # Stateless: connect → execute → close
        async with AsyncExitStack() as stack:
            session = await create_mcp_session(self.server_config, stack, self.user_id)
            await session.initialize()
            result = await session.call_tool(self.tool_name, kwargs)
            return result
        # Connection auto-closes
```

### 2. Type Annotations from JSON Schema
```python
class McpPlugin:
    def _build_annotations(self, input_schema: Dict) -> Dict[str, type]:
        """Convert MCP JSON schema to Python type hints"""
        annotations = {}
        for param_name, param_schema in input_schema.get('properties', {}).items():
            param_type = self._json_type_to_python(param_schema.get('type'))
            annotations[param_name] = param_type
        annotations['return'] = str
        return annotations

    def _add_tool_function(self, tool: McpTool):
        param_annotations = self._build_annotations(tool.input_schema)

        @kernel_function(name=..., description=...)
        async def tool_function(**kwargs):
            return await tool.invoke(**kwargs)

        tool_function.__annotations__ = param_annotations  # SK introspects this!
```

### 3. Catalog Registration (Governance & HITL)
```python
# In McpPluginRegistry._register_tool_in_catalog()
tool_id = f"mcp_{server_name}-{server_name}_{tool_name}"
# Example: "mcp_filesystem-filesystem_read_file"

plugin_tool = PluginTool(
    tool_id=tool_id,
    name=tool_name,
    description=description,
    governance=governance,  # From MCP annotations + overrides
    auth=auth  # OAuth2 if configured
)

catalog.register_dynamic_tool(plugin_tool, plugin_id=f"mcp_{server_name}")
```

### 4. Tool ID Format Consistency
```
MCP Plugin Registration:
  plugin_name = "mcp_filesystem"
  function_name = "filesystem_read_file"

Catalog Registration:
  tool_id = "mcp_filesystem-filesystem_read_file"

HITL Lookup:
  tool_id = f"{plugin_name}-{function_name}"
  = "mcp_filesystem-filesystem_read_file" ✅ MATCHES!
```

## Flow Comparison: MCP vs Non-MCP

### Session Start
| Non-MCP | MCP |
|---------|-----|
| (Code exists in files) | Discover tools → Create plugin CLASSES → Register catalog |

### Agent Build
| Non-MCP | MCP |
|---------|-----|
| Load CLASS from file | Load CLASS from registry |
| Instantiate plugin | Instantiate plugin |
| Add to kernel | Add to kernel |

### Tool Invocation
| Non-MCP | MCP |
|---------|-----|
| HITL check via catalog | HITL check via catalog ✅ SAME! |
| Execute method | Create connection → Execute → Close |

## Benefits Achieved

1. ✅ **MCP tools mirror non-MCP architecture** - Same instantiation pattern
2. ✅ **Catalog integration preserved** - Governance and HITL work identically
3. ✅ **Stateless execution** - Connections created per invocation
4. ✅ **SK schema integration** - Type hints from JSON schema exposed to LLM
5. ✅ **LLM visibility** - Full tool signatures with parameter types
6. ✅ **Separation of concerns** - Discovery vs instantiation vs execution
7. ✅ **Tool ID consistency** - HITL lookup matches catalog registration

## Testing Checklist

To test the implementation:

- [ ] Start application with MCP servers configured
- [ ] Verify MCP discovery logs at first request
- [ ] Check catalog has MCP tools registered
- [ ] Verify HITL works for MCP tools with `requires_hitl: true`
- [ ] Confirm LLM sees MCP tool parameters with types
- [ ] Test stateless execution (connection created per call)
- [ ] Verify governance policies applied correctly
- [ ] Test OAuth2 authentication for MCP servers
- [ ] Check cleanup after requests (no lingering connections)

## Migration Notes

### Breaking Changes
- `McpTool.__init__()` signature changed (removed `client_session`, added `server_config`, `user_id`)
- `McpPlugin.__init__()` `server_name` now required parameter
- `kernel_builder.load_mcp_plugins()` now expects discovery to be done first

### Backward Compatibility
- Old `SessionMcpClientRegistry` can be deprecated but not removed yet
- Existing MCP configs work without changes
- Catalog registration is additive (doesn't break non-MCP tools)

## Next Steps

1. Remove deprecated `_connect_single_mcp_server()` and related old code
2. Add integration tests for complete MCP flow
3. Add metrics/logging for MCP connection lifecycle
4. Document MCP server configuration best practices
5. Consider adding MCP tool output schema support for structured returns
