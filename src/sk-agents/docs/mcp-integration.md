# MCP Integration Guide

This guide explains how to integrate Model Context Protocol (MCP) servers with Teal Agents, enabling your agents to discover and use tools from external MCP servers.

## Overview

The MCP integration provides:

- **Automatic tool discovery** - Tools are discovered at session start and made available to the agent
- **Session-scoped isolation** - Each user session has its own discovered tools and MCP sessions
- **Request-scoped connections** - Connections are pooled within a request and reused for efficiency
- **OAuth 2.1 authentication** - Full support for OAuth2 with PKCE for HTTP MCP servers
- **Governance controls** - HITL (Human-in-the-Loop) integration with secure-by-default policies
- **External state storage** - Redis support for horizontal scaling in production

## Supported Transports

| Transport | Use Case | Authentication |
|-----------|----------|----------------|
| **HTTP** (primary) | Remote MCP servers | OAuth 2.1 with PKCE |
| **stdio** | Local subprocess servers | Environment variables |

> **Note:** HTTP transport is the primary focus of this implementation. stdio transport is supported but secondary.

## Quick Start

### Basic HTTP Server (with OAuth2)

```yaml
apiVersion: tealagents/v1alpha1
name: my-agent
spec:
  name: my-agent
  model: gpt-4
  system_prompt: "You are a helpful assistant with access to external tools."

  mcp_servers:
    - name: github
      url: "https://api.github.com/mcp"
      auth_server: "https://github.com/login/oauth"
      scopes: ["repo", "read:user"]
```

### Basic stdio Server (local)

```yaml
mcp_servers:
  - name: filesystem
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "/safe/directory"
```

## Configuration Reference

### McpServerConfig Fields

#### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Unique identifier for the server |

#### Transport Selection

Transport is inferred automatically:
- If `url` is provided (without `command`) → `http`
- If `command` is provided (without `url`) → `stdio`
- If both provided → must set `transport` explicitly

| Field | Type | Description |
|-------|------|-------------|
| `transport` | `"http"` \| `"stdio"` | Explicit transport selection (optional) |

#### HTTP Transport Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | - | MCP server endpoint URL |
| `auth_server` | string | - | OAuth2 authorization server URL |
| `scopes` | list[string] | `[]` | Required OAuth2 scopes |
| `headers` | dict | - | Non-sensitive HTTP headers (routing, feature flags) |
| `timeout` | float | `30.0` | Connection timeout in seconds |
| `sse_read_timeout` | float | `300.0` | SSE read timeout in seconds |
| `verify_ssl` | bool | `true` | SSL certificate verification |

#### stdio Transport Fields

| Field | Type | Description |
|-------|------|-------------|
| `command` | string | Executable command (e.g., `npx`, `python`) |
| `args` | list[string] | Command arguments |
| `env` | dict | Environment variables for the subprocess |

#### OAuth2 Configuration

| Field | Type | Description |
|-------|------|-------------|
| `oauth_client_id` | string | Pre-registered OAuth client ID |
| `oauth_client_secret` | string | Client secret (confidential clients) |
| `canonical_uri` | string | Explicit canonical URI override |
| `enable_dynamic_registration` | bool | Try RFC 7591 dynamic registration (default: true) |
| `protocol_version` | string | MCP protocol version (e.g., "2025-06-18") |

#### Governance Configuration

| Field | Type | Description |
|-------|------|-------------|
| `trust_level` | `"trusted"` \| `"sandboxed"` \| `"untrusted"` | Server trust level (default: `"untrusted"`) |
| `tool_governance_overrides` | dict | Per-tool governance overrides |

#### User Context

| Field | Type | Description |
|-------|------|-------------|
| `user_id_header` | string | Header name for user ID injection (e.g., `"X-User-Id"`) |
| `user_id_source` | `"auth"` \| `"env"` | Source for user ID value |

## Authentication

### OAuth 2.1 Flow

When an MCP server requires authentication:

```
┌─────────────────────────────────────────────────────────────────┐
│                     OAuth 2.1 Authentication Flow                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. User makes request to agent                                  │
│     └─▶ Discovery starts for MCP servers                        │
│                                                                  │
│  2. No token found for (auth_server, scopes)                    │
│     └─▶ AuthRequiredError raised                                │
│                                                                  │
│  3. Handler generates OAuth authorization URL                    │
│     └─▶ PKCE challenge generated                                │
│     └─▶ State parameter for CSRF protection                     │
│     └─▶ Auth challenge returned to client                       │
│                                                                  │
│  4. User authenticates with OAuth provider                       │
│     └─▶ Redirected to callback with auth code                   │
│                                                                  │
│  5. Code exchanged for tokens                                    │
│     └─▶ Tokens stored in AuthStorage                            │
│     └─▶ Scoped to (user_id, auth_server, scopes)               │
│                                                                  │
│  6. User retries original request                                │
│     └─▶ Token found, discovery succeeds                         │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Token Storage

Tokens are stored with a composite key: `(user_id, auth_server, sorted_scopes)`

This enables:
- Per-user token isolation
- Multiple tokens per user for different servers
- Scope-specific token storage

### Token Refresh

Tokens are automatically refreshed when:
- Access token is expired
- Refresh token is available
- Resource binding matches (if applicable)

## Governance & HITL

### Secure-by-Default Policy

MCP tools use a **secure-by-default** governance model:

| Scenario | HITL Required | Cost | Sensitivity |
|----------|---------------|------|-------------|
| Unknown tool | Yes | High | Sensitive |
| `readOnlyHint: true` | No | Low | Public |
| `destructiveHint: true` | Yes | High | Sensitive |
| High-risk keywords in description | Yes | High | Sensitive |

### Trust Levels

| Trust Level | Behavior |
|-------------|----------|
| `untrusted` (default) | All tools require HITL |
| `sandboxed` | Elevated restrictions, most tools require HITL |
| `trusted` | Use annotation-based governance (still checks for high-risk operations) |

### Governance Overrides

Override automatic governance for specific tools:

```yaml
mcp_servers:
  - name: github
    url: "https://api.github.com/mcp"
    auth_server: "https://github.com/login/oauth"
    scopes: ["repo"]
    trust_level: trusted
    tool_governance_overrides:
      list_repositories:
        requires_hitl: false
        cost: "low"
        data_sensitivity: "public"
      delete_repository:
        requires_hitl: true
        cost: "high"
        data_sensitivity: "sensitive"
```

### Governance Fields

| Field | Values | Description |
|-------|--------|-------------|
| `requires_hitl` | bool | Whether human approval is required |
| `cost` | `"low"` \| `"medium"` \| `"high"` | Resource cost level |
| `data_sensitivity` | `"public"` \| `"proprietary"` \| `"sensitive"` | Data classification |

## Architecture

### Discovery Flow

```
Session Start
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  McpPluginRegistry.discover_and_materialize()                    │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ For each MCP server:                                        │ │
│  │   1. Resolve OAuth tokens (if configured)                   │ │
│  │   2. Connect to MCP server                                  │ │
│  │   3. Initialize MCP session (protocol handshake)            │ │
│  │   4. List tools from server                                 │ │
│  │   5. Register tools in PluginCatalog (for governance)       │ │
│  │   6. Serialize tool data to McpStateManager                 │ │
│  │   7. Close connection                                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  Result: Tools stored in session-scoped state                    │
└─────────────────────────────────────────────────────────────────┘
```

### Request Flow

```
User Request
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  Handler.invoke()                                                │
│                                                                  │
│  1. Check if discovery completed (McpStateManager)               │
│     └─▶ If not, run discovery first                             │
│                                                                  │
│  2. Create McpConnectionManager (request-scoped)                 │
│     └─▶ Load stored MCP session IDs from state                  │
│                                                                  │
│  3. Load MCP plugins into kernel                                 │
│     └─▶ Get tool data from McpStateManager                      │
│     └─▶ Create McpPlugin instances with connection manager      │
│                                                                  │
│  4. Execute agent with LLM                                       │
│     └─▶ Tool calls use connection manager for MCP servers       │
│     └─▶ Connections created lazily on first tool call           │
│     └─▶ Connections reused within request                       │
│                                                                  │
│  5. Cleanup                                                      │
│     └─▶ Persist MCP session IDs to state                        │
│     └─▶ Close all connections                                   │
└─────────────────────────────────────────────────────────────────┘
```

## State Management

### McpStateManager

Stores discovery results and MCP session IDs:

```python
{
    "server_name": {
        "plugin_data": {
            "tools": [...]  # Serialized tool metadata
        },
        "session": {
            "mcp_session_id": "...",  # For stateful MCP servers
            "created_at": "...",
            "last_used_at": "..."
        }
    }
}
```

### Storage Backends

| Backend | Use Case | Configuration |
|---------|----------|---------------|
| In-Memory | Development, testing | Default (no configuration needed) |
| Redis | Production, horizontal scaling | Set environment variables below |

#### In-Memory (Default)

No configuration needed - this is the default for development:

```bash
# These are the defaults, you don't need to set them
export TA_MCP_DISCOVERY_MODULE="sk_agents.mcp_discovery.in_memory_discovery_manager"
export TA_MCP_DISCOVERY_CLASS="InMemoryStateManager"
```

#### Redis (Production)

For production with horizontal scaling, configure Redis storage:

```bash
# Switch to Redis state manager
export TA_MCP_DISCOVERY_MODULE="sk_agents.mcp_discovery.redis_discovery_manager"
export TA_MCP_DISCOVERY_CLASS="RedisStateManager"

# Redis connection (required)
export TA_REDIS_HOST="your-redis-host.example.com"
export TA_REDIS_PORT="6379"
export TA_REDIS_DB="0"

# Redis authentication (optional)
export TA_REDIS_PWD="your-redis-password"
export TA_REDIS_SSL="true"

# State TTL in seconds (optional, default: 86400 = 24 hours)
export TA_REDIS_TTL="86400"
```

### Session Isolation

State is scoped to `(user_id, session_id)`:
- Each user has isolated tools and sessions
- Different sessions for the same user are independent
- Enables multi-tenant deployments

## Configuration Examples

### GitHub MCP Server

```yaml
mcp_servers:
  - name: github
    url: "https://api.github.com/mcp"
    auth_server: "https://github.com/login/oauth"
    scopes: ["repo", "read:user"]
    trust_level: trusted
    tool_governance_overrides:
      create_repository:
        requires_hitl: false
        cost: "medium"
      delete_repository:
        requires_hitl: true
        cost: "high"
```

### Internal API with User Context

```yaml
mcp_servers:
  - name: internal-api
    url: "https://api.internal.example.com/mcp"
    auth_server: "https://auth.internal.example.com/oauth2"
    scopes: ["api.read", "api.write"]
    user_id_header: "X-User-Id"
    user_id_source: "auth"
    headers:
      X-Service-Name: "teal-agents"
```

### Local Filesystem Server

```yaml
mcp_servers:
  - name: filesystem
    command: npx
    args:
      - "@modelcontextprotocol/server-filesystem"
      - "/data/safe-directory"
    env:
      NODE_ENV: production
    trust_level: sandboxed
```

### SQLite Database Server

```yaml
mcp_servers:
  - name: sqlite
    command: python
    args:
      - "-m"
      - "mcp_server_sqlite"
      - "--db-path"
      - "/data/app.db"
    tool_governance_overrides:
      execute_query:
        requires_hitl: true
        cost: "medium"
```

### Multiple Servers

```yaml
mcp_servers:
  # Remote authenticated server
  - name: github
    url: "https://api.github.com/mcp"
    auth_server: "https://github.com/login/oauth"
    scopes: ["repo"]
    trust_level: trusted

  # Local filesystem access
  - name: filesystem
    command: npx
    args: ["@modelcontextprotocol/server-filesystem", "/data"]
    trust_level: sandboxed

  # Internal API
  - name: analytics
    url: "https://analytics.internal.example.com/mcp"
    auth_server: "https://auth.internal.example.com/oauth2"
    scopes: ["analytics.read"]
```

## Environment Variables

### MCP State Storage

See [Storage Backends](#storage-backends) section above for detailed configuration examples.

| Variable | Description | Default |
|----------|-------------|---------|
| `TA_MCP_DISCOVERY_MODULE` | Python module for state manager | `sk_agents.mcp_discovery.in_memory_discovery_manager` |
| `TA_MCP_DISCOVERY_CLASS` | State manager class name | `InMemoryStateManager` |
| `TA_REDIS_HOST` | Redis host (when using Redis) | - |
| `TA_REDIS_PORT` | Redis port | `6379` |
| `TA_REDIS_DB` | Redis database number | `0` |
| `TA_REDIS_PWD` | Redis password | - |
| `TA_REDIS_SSL` | Enable SSL for Redis | `false` |
| `TA_REDIS_TTL` | State TTL in seconds | `86400` (24h) |

### OAuth Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `TA_OAUTH_CLIENT_NAME` | Default OAuth client name | - |
| `TA_MCP_OAUTH_HTTPS_REQUIRED` | Enforce HTTPS for OAuth endpoints | `true` |

## Troubleshooting

### Common Issues

#### "AuthRequiredError" on first request

This is expected behavior. The user needs to complete OAuth authentication:
1. Client receives auth challenge with `auth_url`
2. User visits URL and authenticates
3. Callback stores tokens
4. Retry original request

#### "No tools discovered"

Check:
1. MCP server is running and accessible
2. Server returns tools from `list_tools()`
3. Authentication is configured correctly (for HTTP)
4. Network connectivity to server

#### "Connection timeout"

Increase timeout values:
```yaml
mcp_servers:
  - name: slow-server
    url: "https://api.example.com/mcp"
    timeout: 60.0
    sse_read_timeout: 600.0
```

#### "HITL required for all tools"

Check trust level - default is `untrusted` which requires HITL for everything:
```yaml
mcp_servers:
  - name: my-server
    trust_level: trusted  # or sandboxed
```

### Debug Logging

Enable detailed logging:

```python
import logging

logging.getLogger('sk_agents.mcp_client').setLevel(logging.DEBUG)
logging.getLogger('sk_agents.mcp_plugin_registry').setLevel(logging.DEBUG)
logging.getLogger('sk_agents.mcp_discovery').setLevel(logging.DEBUG)
```

## Known Limitations

1. **OAuth 2.1 end-to-end testing**: OAuth implementation is complete but not tested end-to-end with real OAuth providers. Unit tests use mocked tokens.

2. **stdio transport**: Supported but not the primary focus. HTTP transport is recommended for production use.

3. **WebSocket transport**: Not yet supported (pending MCP SDK support).

4. **Tool hot-reload**: Tools are discovered at session start only. Changes require a new session.

## Security Considerations

1. **Credential handling**: OAuth tokens are stored securely in AuthStorage with user isolation
2. **Secret sanitization**: Secrets are stripped from serialized state
3. **HTTPS enforcement**: OAuth flows require HTTPS by default
4. **Trust boundaries**: Use appropriate trust levels for different server types
5. **HITL for destructive operations**: Secure-by-default ensures human oversight
