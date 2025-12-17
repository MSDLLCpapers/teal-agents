# MCP Integration PR Review Guide

This guide helps reviewers understand, test, and review the MCP (Model Context Protocol) integration.

## PR Summary

This PR introduces MCP support to Teal Agents, enabling agents to discover and use tools from external MCP servers. The integration follows a **session-scoped discovery, request-scoped connection** pattern that supports horizontal scaling.

### Key Features

| Feature | Description |
|---------|-------------|
| **HTTP Transport** | Primary focus - connects to remote MCP servers |
| **Session-Scoped Discovery** | Tools discovered once per session, stored externally |
| **Request-Scoped Connections** | Lazy connection pooling within each request |
| **Governance/HITL** | Secure-by-default with trust levels |
| **External State Storage** | In-memory (dev) or Redis (prod) |

### Known Limitations

1. **OAuth 2.1**: Implemented and unit tested, but NOT tested end-to-end with real OAuth providers
2. **stdio transport**: Supported but secondary to HTTP transport

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         SESSION START                                 │
├──────────────────────────────────────────────────────────────────────┤
│  McpPluginRegistry.discover_and_materialize()                        │
│    ├── For each MCP server:                                          │
│    │     ├── Resolve OAuth tokens (if configured)                    │
│    │     ├── Connect to MCP server                                   │
│    │     ├── List tools from server                                  │
│    │     ├── Register tools in PluginCatalog (governance)            │
│    │     └── Store tool metadata in McpStateManager                  │
│    └── Close connections (discovery complete)                        │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         EACH REQUEST                                  │
├──────────────────────────────────────────────────────────────────────┤
│  Handler.invoke()                                                     │
│    ├── Create McpConnectionManager (request-scoped)                  │
│    ├── Load McpPlugin instances from stored state                    │
│    ├── Execute agent with LLM                                        │
│    │     └── Tool calls use connection_manager.get_connection()      │
│    │         (connections created lazily, reused within request)     │
│    └── Cleanup: close all connections                                │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Recommended Review Order

Review files in this order to build understanding progressively:

### 1. Configuration (Start Here)
Understand how MCP servers are configured:

| File | Purpose |
|------|---------|
| `sk_agents/tealagents/v1alpha1/config.py` | `McpServerConfig` - all config options |

### 2. State Management
Understand how discovery state is stored:

| File | Purpose |
|------|---------|
| `sk_agents/mcp_discovery/mcp_discovery_manager.py` | `McpState` model, `DiscoveryManager` interface |
| `sk_agents/mcp_discovery/in_memory_discovery_manager.py` | Default in-memory implementation |
| `sk_agents/mcp_discovery/redis_discovery_manager.py` | Production Redis implementation |

### 3. Connection Management
Understand request-scoped connection pooling:

| File | Purpose |
|------|---------|
| `sk_agents/mcp_connection_manager.py` | `McpConnectionManager` - lazy connections |

### 4. Discovery & Plugin Registration
Understand how tools are discovered:

| File | Purpose |
|------|---------|
| `sk_agents/mcp_plugin_registry.py` | `McpPluginRegistry` - discovery orchestration |
| `sk_agents/mcp_client.py` | `McpTool`, `McpPlugin` - SK integration |

### 5. Handler Integration
Understand how it all comes together:

| File | Purpose |
|------|---------|
| `sk_agents/tealagents/v1alpha1/agent/handler.py` | Handler integration points |

### 6. Authentication
Understand OAuth 2.1 flow:

| File | Purpose |
|------|---------|
| `sk_agents/auth/oauth21_client.py` | OAuth 2.1 with PKCE implementation |
| `sk_agents/auth_storage/` | Token storage abstraction |

---

## Testing Guide

### Running Unit Tests

```bash
# Run all MCP tests
cd src/sk-agents
pytest tests/mcp/ -v

# Run specific test categories
pytest tests/mcp/test_mcp_client.py -v           # Core MCP client tests
pytest tests/mcp/test_connection_manager.py -v   # Connection management
pytest tests/mcp/test_state_manager.py -v        # State persistence
pytest tests/mcp/test_plugin_registry.py -v      # Discovery flow
pytest tests/mcp/test_auth*.py -v                # Authentication tests

# Expected result: 140 passed, 5 skipped
```

### Local Integration Testing

To test with a real MCP server (like Arcade), follow this pattern:

#### 1. Set Up Environment

#### 2. Create Agent Config

```yaml
# config.yaml
apiVersion: tealagents/v1alpha1
kind: Chat
name: TestAgent
spec:
  agent:
    name: test_agent
    role: Test Assistant
    model: gpt-4o-mini
    system_prompt: >
      You are a helpful assistant with access to external tools.

    mcp_servers:
      # Arcade MCP Server (requires API key)
      - name: arcade
        transport: http
        url: https://api.arcade.dev/mcp/your-project-id
        headers:
          Authorization: "Bearer your-arcade-api-key"
        user_id_header: Arcade-User-Id
        user_id_source: env
        user_id_env_var: ARCADE_USER_ID
        trust_level: trusted
        verify_ssl: false

      # AWS Knowledge MCP (public, no auth)
      - name: aws-knowledge
        transport: http
        url: https://knowledge-mcp.global.api.aws
        trust_level: trusted
        verify_ssl: false
```

#### 3. Run the Agent

```python
# run_agent.py
import uvicorn
from sk_agents.tealagents.v1alpha1.chat_runner import TealAgentsV1Alpha1ChatRunner

runner = TealAgentsV1Alpha1ChatRunner("config.yaml")
app = runner.app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

```bash
# Start the agent
python run_agent.py

# Test with curl
curl -X POST http://localhost:8000/tealagents/v1alpha1/chat \
  -H "Content-Type: application/json" \
  -d '{"messages": [{"role": "user", "content": "What tools do you have access to?"}]}'
```

### What to Verify During Testing

| Aspect | How to Verify |
|--------|---------------|
| **Discovery** | Check logs for "Discovered N tools from server X" |
| **Tool Registration** | Ask agent "What tools do you have?" |
| **Tool Execution** | Invoke an MCP tool and verify response |
| **Connection Reuse** | Multiple tool calls in one request should reuse connection |
| **Error Handling** | Test with invalid server URL - should fail gracefully |

---

## Key Files to Focus On

### Critical Path (Must Review)

| File | Lines Changed | Complexity |
|------|---------------|------------|
| `mcp_connection_manager.py` | ~200 | High - core connection logic |
| `mcp_plugin_registry.py` | ~300 | High - discovery orchestration |
| `mcp_client.py` | ~400 | High - SK integration |
| `mcp_discovery/mcp_discovery_manager.py` | ~100 | Medium - state model |

### Supporting Files (Quick Review)

| File | Purpose |
|------|---------|
| `mcp_discovery/in_memory_discovery_manager.py` | In-memory state storage |
| `mcp_discovery/redis_discovery_manager.py` | Redis state storage |
| `auth/oauth21_client.py` | OAuth implementation |

### Test Files (Verify Coverage)

| File | What It Tests |
|------|---------------|
| `tests/mcp/test_mcp_client.py` | McpTool, McpPlugin, governance mapping |
| `tests/mcp/test_connection_manager.py` | Connection lifecycle, pooling |
| `tests/mcp/test_state_manager.py` | State persistence, isolation |
| `tests/mcp/test_plugin_registry.py` | Discovery flow |

---

## Configuration Quick Reference

### Minimal HTTP Config

```yaml
mcp_servers:
  - name: my-server
    url: https://api.example.com/mcp
```

### Full HTTP Config with OAuth

```yaml
mcp_servers:
  - name: github
    transport: http
    url: https://api.github.com/mcp
    auth_server: https://github.com/login/oauth
    scopes: ["repo", "read:user"]
    trust_level: trusted
    timeout: 30.0
    sse_read_timeout: 300.0
    verify_ssl: true
    tool_governance_overrides:
      delete_repository:
        requires_hitl: true
        cost: high
```

### State Manager Configuration

```bash
# In-Memory (Default - for development)
# No configuration needed

# Redis (Production)
export TA_MCP_DISCOVERY_MODULE="sk_agents.mcp_discovery.redis_discovery_manager"
export TA_MCP_DISCOVERY_CLASS="RedisStateManager"
export TA_REDIS_HOST="your-redis-host"
export TA_REDIS_PORT="6379"
export TA_REDIS_DB="0"
export TA_REDIS_PWD="your-password"  # optional
export TA_REDIS_SSL="true"           # optional
export TA_REDIS_TTL="86400"          # optional, default 24h
```

---

## Common Review Questions

### Q: Why session-scoped discovery instead of per-request?

**A:** Tool discovery involves HTTP calls to MCP servers and catalog registration. Doing this per-request would be slow and wasteful. Discovery happens once per session, with state stored externally (Redis in prod) to support horizontal scaling.

### Q: Why request-scoped connections instead of persistent?

**A:** MCP connections are stateful and tied to a specific MCP session. Request-scoped connections:
- Avoid connection staleness issues
- Work correctly with load balancers
- Allow clean resource cleanup
- Are lazy (only created when tools are actually called)

### Q: How does auth work across multiple servers?

**A:** Each MCP server can have its own OAuth configuration. Tokens are stored with a composite key: `(user_id, auth_server, sorted_scopes)`. This allows:
- Per-user token isolation
- Multiple tokens per user for different servers
- Scope-specific token storage

### Q: What happens if an MCP server is down?

**A:** Discovery continues for other servers - one failure doesn't block others. Failed servers are logged and their tools won't be available. At runtime, tool calls to unavailable servers will raise appropriate errors.

---

## Documentation Links

| Document | Purpose |
|----------|---------|
| [MCP Integration Guide](mcp-integration.md) | User-facing configuration guide |
| [MCP Client Specification](mcp-client-specification.md) | Technical architecture spec |
| [MCP Tests README](../tests/mcp/README.md) | Testing documentation |
