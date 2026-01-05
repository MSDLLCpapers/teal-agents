# MCP Testing Guide

This directory contains comprehensive tests for the MCP (Model Context Protocol) integration in Teal Agents.

## Test Overview

**Test Results:** 135 passed, 5 skipped

| Test File | Tests | Description |
|-----------|-------|-------------|
| `test_mcp_client.py` | 28 | Unit tests for core MCP client functionality |
| `test_mcp_plugin_registry.py` | 16 | Integration tests for tool discovery |
| `test_mcp_integration.py` | 4 | End-to-end integration validation |
| `test_handler_integration.py` | 10 | Handler-level MCP flows (5 skipped) |
| `test_auth_separation.py` | 12 | OAuth2 authentication separation |
| `test_oauth_*.py` | 25+ | OAuth2 compliance tests |
| `test_server_metadata_discovery.py` | 10 | RFC 8414/9728 metadata discovery |

## Running Tests

### Run All MCP Tests

```bash
# From sk-agents directory
python -m pytest tests/mcp/ -v

# With coverage
python -m pytest tests/mcp/ --cov=sk_agents.mcp_client --cov=sk_agents.mcp_plugin_registry --cov-report=html
```

### Run Specific Test File

```bash
python -m pytest tests/mcp/test_mcp_client.py -v
python -m pytest tests/mcp/test_mcp_plugin_registry.py -v
python -m pytest tests/mcp/test_auth_separation.py -v
```

### Run Specific Test Class

```bash
python -m pytest tests/mcp/test_mcp_client.py::TestAuthHeaderResolution -v
python -m pytest tests/mcp/test_mcp_client.py::TestGovernanceMapping -v
```

### Run Specific Test

```bash
python -m pytest tests/mcp/test_mcp_client.py::TestGovernanceMapping::test_destructive_tool_requires_hitl -v
```

## Testing Philosophy

### Three-Tier Testing Approach

```
Tier 1: Unit Tests
├── Mock OAuth2AuthData fixtures (no real OAuth flows)
├── Mock MCP SDK ClientSession (no real MCP servers)
├── Pure logic testing without external dependencies
└── Focus: Individual functions and classes

Tier 2: Integration Tests
├── Mock MCP servers with realistic responses
├── End-to-end discovery flow testing
├── Tool execution with mocked connections
└── Focus: Component interactions

Tier 3: Manual/E2E Tests (Optional)
├── Real OAuth2 flows (when providers available)
├── Real MCP servers (local or remote)
└── Focus: Production validation
```

### Key Testing Principles

1. **No Real OAuth2 Flows**: OAuth2 is just data - we test logic with mock tokens
2. **No Real MCP Servers**: MCP SDK components are mocked with realistic behavior
3. **Realistic Mock Behavior**: Mocks simulate token expiration, scope validation, etc.
4. **Defense-in-Depth Testing**: Multiple layers verified (config → runtime → execution)
5. **Per-User Context**: Tests verify user_id propagation throughout the system

## Test Files

### `conftest.py` - Shared Fixtures

**OAuth2 Fixtures:**
```python
@pytest.fixture
def mock_oauth2_token():
    """Valid OAuth2 token (expires in 1 hour)."""
    return OAuth2AuthData(
        access_token="mock_access_token_12345",
        refresh_token="mock_refresh_token_67890",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        scopes=["read", "write"],
    )

@pytest.fixture
def expired_oauth2_token():
    """Expired OAuth2 token for expiration handling tests."""
    return OAuth2AuthData(
        access_token="expired_token",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        scopes=["read"],
    )
```

**MCP Server Config Fixtures:**
```python
@pytest.fixture
def http_mcp_config():
    """HTTP transport config with OAuth2."""
    return McpServerConfig(
        name="test-http",
        transport="http",
        url="https://test.example.com/mcp",
        auth_server="https://auth.example.com",
        scopes=["read", "write"],
    )

@pytest.fixture
def stdio_mcp_config():
    """Stdio transport config."""
    return McpServerConfig(
        name="test-stdio",
        transport="stdio",
        command="npx",
        args=["@modelcontextprotocol/server-test"],
    )

@pytest.fixture
def github_mcp_config():
    """GitHub-like config with governance overrides."""
    return McpServerConfig(
        name="github",
        transport="http",
        url="https://api.github.com/mcp",
        auth_server="https://github.com/login/oauth",
        scopes=["repo", "read:user"],
        trust_level="trusted",
        tool_governance_overrides={
            "delete_repository": GovernanceOverride(
                requires_hitl=True,
                cost="high",
            ),
        },
    )
```

**MCP SDK Mocks:**
```python
@pytest.fixture
def mock_mcp_tool():
    """Mock MCP tool with realistic structure."""
    return MagicMock(
        name="test_tool",
        description="A test tool",
        inputSchema={
            "type": "object",
            "properties": {"input": {"type": "string"}},
            "required": ["input"],
        },
        annotations={"readOnlyHint": True},
    )

@pytest.fixture
def mock_mcp_session():
    """Mock ClientSession avoiding real connections."""
    session = AsyncMock(spec=ClientSession)
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[...]))
    session.call_tool = AsyncMock(return_value=MagicMock(
        isError=False,
        content=[MagicMock(text="result")],
    ))
    return session
```

**Cleanup Fixtures:**
```python
@pytest.fixture(autouse=True)
def cleanup_mcp_registry():
    """Auto-cleanup MCP registry after each test."""
    yield
    McpPluginRegistry.clear()
```

### `test_mcp_client.py` - Unit Tests

**TestAuthStorageKeyBuilder** (4 tests)
- Key building with multiple scopes
- Scope sorting for consistency
- Handling empty scopes
- Special characters in auth_server

**TestGovernanceMapping** (5 tests)
- Destructive tool mapping → `requires_hitl=True`
- Read-only tool mapping → `requires_hitl=False`
- Unknown tools → secure by default
- Risky keywords in descriptions
- Network operation detection

**TestTrustLevelGovernance** (4 tests)
- Untrusted servers force HITL
- Sandboxed servers require HITL
- Trusted servers with safe operations
- Trusted servers with risky operations (defense in depth)

**TestGovernanceOverrides** (4 tests)
- Override HITL requirement
- Override all governance fields
- Missing override returns base governance
- None overrides returns base governance

**TestAuthHeaderResolution** (6 tests)
- Valid token resolution
- Expired token handling
- Missing token handling (AuthRequiredError)
- Non-sensitive header forwarding
- Static Authorization header blocking
- OAuth2 token priority over static headers

**TestMcpTool** (2 tests)
- Tool initialization
- Input validation

**TestMcpPlugin** (3 tests)
- Requires user_id (ValueError if empty)
- Successful initialization with user_id
- Creates kernel functions for each tool

### `test_mcp_plugin_registry.py` - Integration Tests

**TestRegistryDiscovery** (4 tests)
- Discover single server
- Discover multiple servers
- Discovery continues on server failure
- Auth errors collected and raised

**TestPluginInstantiation** (3 tests)
- Instantiate with user_id
- Multiple instances for different users
- Same class, different user contexts

**TestCatalogRegistration** (5 tests)
- Tools registered in catalog
- Governance applied to catalog tools
- Governance overrides from config
- OAuth2 auth registered for HTTP servers
- Trust level affects governance

**TestRegistryUtilities** (4 tests)
- Get tools for session
- Get nonexistent server returns empty
- Serialization excludes secrets
- Deserialization restores tools

### `test_handler_integration.py` - Handler Tests

> **Note:** Some tests are skipped pending refactoring after McpConnectionManager changes.

**TestSessionStartDiscovery** (3 tests, skipped)
- Discovery runs on first request
- Discovery runs only once per session
- Discovery skipped when no MCP servers

**TestAuthChallenge** (1 test, skipped)
- Auth challenge contains correct resume URL

**TestResumeFlow** (1 test, skipped)
- Resume loads MCP plugins with user_id

**TestUserIdPropagation** (2 tests)
- user_id passed to discovery
- user_id passed to agent builder

**TestErrorHandling** (2 tests)
- Discovery failures logged but don't crash
- Missing user_id raises clear error

### `test_auth_separation.py` - Auth Separation Tests

**TestAuthKeyIsolation** (4 tests)
- Different servers get different storage keys
- Same server, different scopes get different keys
- Scope order doesn't affect key

**TestPerUserTokens** (4 tests)
- User A's token not visible to User B
- Each user has isolated token storage
- Token updates don't affect other users

**TestAuthChallengeFlow** (4 tests)
- Auth challenge includes server info
- Multiple servers can require auth
- Auth challenge includes resume URL

### OAuth2 Compliance Tests

**`test_oauth_https_enforcement.py`** (8 tests)
- HTTPS required for auth_server
- HTTP rejected by default
- Environment variable can disable (dev only)

**`test_oauth_scope_validation.py`** (8 tests)
- Scope escalation detected
- Scope reduction allowed
- Empty scopes handled

**`test_oauth_www_authenticate.py`** (10 tests)
- WWW-Authenticate header parsing
- Error code extraction
- Scope extraction for insufficient_scope

**`test_oauth_protocol_version.py`** (6 tests)
- Resource parameter included for 2025-06-18+
- Resource parameter omitted for older versions
- PRM discovery affects resource inclusion

**`test_server_metadata_discovery.py`** (10 tests)
- RFC 8414 metadata discovery
- RFC 9728 PRM discovery
- Fallback when discovery fails

## Common Test Patterns

### Pattern 1: Mocking AuthStorageFactory

```python
@patch("sk_agents.mcp_client.AuthStorageFactory")
@patch("sk_agents.mcp_client.AppConfig")
def test_resolve_with_valid_token(self, mock_app_config, mock_factory, mock_oauth2_token):
    # Setup mocks
    mock_storage = MagicMock()
    mock_storage.retrieve.return_value = mock_oauth2_token
    mock_factory.return_value.get_auth_storage_manager.return_value = mock_storage

    # Test
    config = McpServerConfig(
        name="test",
        url="https://test.com/mcp",
        auth_server="https://auth.com",
        scopes=["read"],
    )
    headers = resolve_server_auth_headers(config, "test_user")

    # Verify
    assert headers["Authorization"] == "Bearer mock_access_token_12345"
    mock_storage.retrieve.assert_called_once()
```

### Pattern 2: Testing Governance Application

```python
def test_governance_with_overrides(self):
    # Setup
    base = Governance(
        requires_hitl=True,
        cost="high",
        data_sensitivity="sensitive",
    )
    overrides = {
        "safe_tool": GovernanceOverride(
            requires_hitl=False,
            cost="low",
        ),
    }

    # Test
    result = apply_governance_overrides(base, "safe_tool", overrides)

    # Verify
    assert result.requires_hitl is False  # Overridden
    assert result.cost == "low"  # Overridden
    assert result.data_sensitivity == "sensitive"  # Kept from base
```

### Pattern 3: Async MCP Discovery Testing

```python
@pytest.mark.asyncio
@patch("sk_agents.mcp_plugin_registry.create_mcp_session_with_retry")
@patch("sk_agents.mcp_plugin_registry.resolve_server_auth_headers")
async def test_discovery_success(
    self,
    mock_resolve_auth,
    mock_create_session,
    http_mcp_config,
    mock_mcp_session,
    mock_discovery_manager,
):
    # Setup
    mock_resolve_auth.return_value = {"Authorization": "Bearer token"}
    mock_create_session.return_value = (mock_mcp_session, lambda: "session-id")

    # Test
    await McpPluginRegistry.discover_and_materialize(
        [http_mcp_config],
        "test_user",
        "session_123",
        mock_discovery_manager,
        MagicMock(),
    )

    # Verify
    mock_discovery_manager.mark_completed.assert_called_once()
```

### Pattern 4: Testing AuthRequiredError

```python
@pytest.mark.asyncio
@patch("sk_agents.mcp_client.AuthStorageFactory")
async def test_missing_token_raises_auth_error(self, mock_factory):
    # Setup - no token in storage
    mock_storage = MagicMock()
    mock_storage.retrieve.return_value = None
    mock_factory.return_value.get_auth_storage_manager.return_value = mock_storage

    config = McpServerConfig(
        name="test",
        url="https://test.com/mcp",
        auth_server="https://auth.com",
        scopes=["read"],
    )

    # Test & Verify
    with pytest.raises(AuthRequiredError) as exc_info:
        await resolve_server_auth_headers(config, "test_user")

    assert exc_info.value.server_name == "test"
    assert exc_info.value.auth_server == "https://auth.com"
    assert exc_info.value.scopes == ["read"]
```

## Troubleshooting

### Issue: "AuthStorageFactory not mocked"

**Solution:** Add `@patch("sk_agents.mcp_client.AuthStorageFactory")` to test method.

The patch path must match where the import is used, not where it's defined.

### Issue: "AsyncMock not working"

**Solution:**
1. Mark test with `@pytest.mark.asyncio`
2. Use `async def test_...`
3. Use `await` when calling async functions

### Issue: "Mock not called"

**Solution:**
1. Check you're testing the right code path
2. Use `assert_called_once()` to verify
3. Check patch path matches import location

### Issue: "Registry has stale data"

**Solution:**
1. Use `cleanup_mcp_registry` fixture (auto-cleanup)
2. Or call `McpPluginRegistry.clear()` manually
3. Or use `reset_mcp_registry` fixture

### Issue: "Test passes locally, fails in CI"

**Common causes:**
1. Time-dependent tests (use `freezegun` or fixed timestamps)
2. Environment variables not set
3. Order-dependent tests (ensure proper isolation)

## Adding New Tests

### 1. Identify Test Category

| Category | File | Focus |
|----------|------|-------|
| Core client logic | `test_mcp_client.py` | Functions, classes |
| Discovery flow | `test_mcp_plugin_registry.py` | Integration |
| Handler integration | `test_handler_integration.py` | Full flow |
| OAuth2 compliance | `test_oauth_*.py` | RFC compliance |
| Auth separation | `test_auth_separation.py` | Multi-user |

### 2. Add Fixture to `conftest.py` (if needed)

```python
@pytest.fixture
def my_custom_fixture():
    """Description of what this fixture provides."""
    return SomeObject(...)
```

### 3. Create Test Class

```python
class TestMyFeature:
    """Test my feature."""

    def test_basic_behavior(self, my_custom_fixture):
        # Arrange
        input_data = ...

        # Act
        result = my_function(input_data)

        # Assert
        assert result == expected
```

### 4. Use Appropriate Mocks

```python
# For OAuth2 testing
@patch("sk_agents.mcp_client.AuthStorageFactory")
def test_with_auth(self, mock_factory, mock_oauth2_token):
    mock_factory.return_value.get_auth_storage_manager.return_value.retrieve.return_value = mock_oauth2_token
    ...

# For MCP session testing
@patch("sk_agents.mcp_plugin_registry.create_mcp_session_with_retry")
async def test_with_mcp(self, mock_create, mock_mcp_session):
    mock_create.return_value = (mock_mcp_session, lambda: "id")
    ...
```

### 5. Mark Async Tests

```python
@pytest.mark.asyncio
async def test_async_operation(self):
    result = await some_async_function()
    assert result == expected
```

## Coverage Goals

**Current Coverage Areas:**
- Auth storage key building
- OAuth2 token resolution
- Governance mapping and overrides
- Trust level application
- Plugin class creation
- Tool catalog registration
- Discovery flow
- Handler integration (partial)
- User ID propagation

**Target:** 90%+ coverage for:
- `mcp_client.py`
- `mcp_plugin_registry.py`
- `mcp_discovery/*.py`

## Known Skipped Tests

The following tests are skipped pending refactoring:

| Test | Reason |
|------|--------|
| `TestSessionStartDiscovery` | McpConnectionManager changes |
| `TestAuthChallenge` | StateManagerFactory removed from handler |
| `TestResumeFlow` | Handler architecture changed |

These tests need to be updated to mock the new `DiscoveryManagerFactory` and `McpConnectionManager` instead of the removed `StateManagerFactory`.

## Related Documentation

- **MCP Integration Guide**: `docs/mcp-integration.md`
- **MCP Client Specification**: `docs/mcp-client-specification.md`
- **Auth Storage Tests**: `tests/auth_storage/` (similar mocking patterns)
- **Pytest Fixtures**: https://docs.pytest.org/en/stable/fixture.html
- **unittest.mock**: https://docs.python.org/3/library/unittest.mock.html
