# Add MCP (Model Context Protocol) Integration

Introduces MCP support enabling agents to discover and use tools from external MCP servers.

## Changes

- Add HTTP transport with OAuth 2.1 (PKCE) authentication
- Add stdio transport for local subprocess MCP servers
- Add session-scoped tool discovery with external state storage
- Add request-scoped connection pooling for horizontal scaling
- Add governance/HITL integration with secure-by-default policies
- Add trust levels (trusted/sandboxed/untrusted) for MCP servers
- Add tool governance overrides for fine-grained control
- Add Redis state manager for production deployments
- Add in-memory state manager for development
- Add user ID propagation to MCP servers
- Add comprehensive test coverage (140 tests)

## Key Components

- `McpServerConfig` - MCP server configuration model
- `McpConnectionManager` - Request-scoped lazy connection pooling
- `McpPluginRegistry` - Tool discovery and catalog registration
- `McpTool` - Individual MCP tool representation
- `McpPlugin` - Semantic Kernel plugin wrapping MCP tools
- `McpState` - Discovery state model
- `InMemoryStateManager` - Development state storage
- `RedisStateManager` - Production state storage
- `OAuth21Client` - OAuth 2.1 with PKCE implementation
- `AuthStorage` - Per-user token storage

## Known Limitations

- OAuth 2.1 not end-to-end tested with real providers
- HTTP transport is primary focus (stdio secondary)

## Docs

- `docs/mcp-integration.md` - User-facing configuration guide
- `docs/mcp-client-specification.md` - Technical architecture spec
- `docs/MCP_PR_REVIEW_GUIDE.md` - Detailed review instructions


  | Category                         | Files | Lines   |
  |----------------------------------|-------|---------|
  | Source code (src/sk-agents/src/) | 27    | +6,231  |
  | Tests (src/sk-agents/tests/)     | 15    | +3,997  |
  | Documentation (.md files)        | 5     | +2,459  |
  | Other (examples, configs)        | 8     | ~150    |
  | Total                            | 55    | +12,840 |
