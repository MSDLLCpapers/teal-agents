# MCP Testing Guide

This directory contains comprehensive tests for the MCP (Model Context Protocol) integration without requiring real OAuth2 flows or actual MCP servers.

## Testing Philosophy

**Three-Tier Testing Approach:**

```
Tier 1: Unit Tests (Current Implementation)
├── Mock OAuth2AuthData fixtures
├── Mock AuthStorageFactory with @patch decorators
├── Mock MCP SDK ClientSession
└── Pure logic testing without external dependencies

Tier 2: Integration Tests (Current Implementation)
├── Mock MCP servers
├── End-to-end discovery flow
└── Tool execution with mocked connections

Tier 3: E2E Tests (Optional/Manual)
└── Real OAuth2 flows for production validation
```

## How OAuth2 is Mocked

The key insight: **OAuth2 is just data**. We don't need real OAuth2 flows to test MCP logic.

### Mocking Strategy

1. **OAuth2AuthData Fixtures** (`conftest.py`)
   - `mock_oauth2_token`: Valid token (expires in 1 hour)
   - `expired_oauth2_token`: Expired token (for expiration handling)

2. **AuthStorage Mocking**
   - `mock_auth_storage`: Simulates `InMemorySecureAuthStorageManager`
   - Pre-populated with tokens for `test_user`
   - Uses `MagicMock` with side_effect for realistic behavior

3. **AuthStorageFactory Mocking**
   - `@patch("sk_agents.mcp_client.AuthStorageFactory")` in tests
   - Returns mock auth storage with pre-configured tokens
   - Tests token resolution without real OAuth2 flows

### Example Test Pattern

```python
@patch("sk_agents.mcp_client.AuthStorageFactory")
@patch("sk_agents.mcp_client.AppConfig")
def test_resolve_with_valid_token(self, mock_app_config, mock_factory, mock_oauth2_token):
    # Setup mocks
    mock_storage = MagicMock()
    mock_storage.retrieve.return_value = mock_oauth2_token
    mock_factory.return_value.get_auth_storage_manager.return_value = mock_storage

    # Test
    config = McpServerConfig(...)
    headers = resolve_server_auth_headers(config, "test_user")

    # Verify
    assert headers["Authorization"] == "Bearer mock_access_token_12345"
```

## Test Files

### `conftest.py` - Test Fixtures

**OAuth2 Fixtures:**
- `mock_oauth2_token`: Valid OAuth2 token
- `expired_oauth2_token`: Expired token
- `mock_auth_storage`: Mock auth storage manager
- `mock_auth_storage_factory`: Factory returning mock storage

**MCP Server Config Fixtures:**
- `stdio_mcp_config`: Stdio transport config
- `http_mcp_config`: HTTP transport with OAuth2
- `github_mcp_config`: GitHub-like config with governance overrides

**MCP SDK Mocks:**
- `mock_mcp_tool`: Mock MCP tool with realistic structure
- `mock_destructive_tool`: Mock tool with destructive annotation
- `mock_mcp_session`: Mock ClientSession avoiding real connections

**Utilities:**
- `reset_mcp_registry`: Cleanup between tests
- `cleanup_mcp_registry`: Auto-cleanup after each test
- `mock_kernel`: Mock Semantic Kernel
- `mock_extra_data_collector`: Mock data collector

### `test_mcp_client.py` - Unit Tests (28 tests)

**TestAuthStorageKeyBuilder (4 tests):**
- Key building with multiple scopes
- Scope sorting for consistency
- Handling empty scopes

**TestGovernanceMapping (5 tests):**
- Destructive tool mapping → requires_hitl=True
- Read-only tool mapping → requires_hitl=False
- Unknown tools → secure by default
- Risky keywords in descriptions
- Network operation detection

**TestTrustLevelGovernance (4 tests):**
- Untrusted servers force HITL
- Sandboxed servers require HITL
- Trusted servers with safe operations
- Trusted servers with risky operations (defense in depth)

**TestGovernanceOverrides (4 tests):**
- Override HITL requirement
- Override all governance fields
- Missing override returns base governance
- None overrides returns base governance

**TestAuthHeaderResolution (6 tests):**
- Valid token resolution
- Expired token handling
- Missing token handling
- Non-sensitive header forwarding
- Static Authorization header blocking
- OAuth2 token priority over static headers

**TestMcpTool (2 tests):**
- Tool initialization
- Input validation

**TestMcpPlugin (3 tests):**
- Requires user_id (ValueError if empty)
- Successful initialization with user_id
- Creates kernel functions for each tool

### `test_mcp_plugin_registry.py` - Integration Tests (16+ tests)

**TestRegistryDiscovery:**
- Discover single server
- Discover multiple servers
- Discovery continues on failure

**TestPluginInstantiation:**
- Instantiate with user_id
- Multiple instances for different users
- Same class, different user contexts

**TestCatalogRegistration:**
- Tools registered in catalog
- Governance applied to catalog tools
- Governance overrides from config
- OAuth2 auth registered for HTTP servers

**TestRegistryUtilities:**
- Get nonexistent plugin class
- Get all plugin classes
- Clear registry

### `test_handler_integration.py` - Handler Tests (10+ tests)

**TestSessionStartDiscovery:**
- Discovery runs on first request
- Discovery runs only once
- Discovery skipped when no MCP servers

**TestAuthChallenge:**
- Auth challenge contains correct resume URL
- Resume URL format: `/tealagents/v1alpha1/resume/{request_id}`

**TestResumeFlow:**
- Resume loads MCP plugins with user_id

**TestUserIdPropagation:**
- user_id passed to discovery
- user_id passed to agent builder
- user_id propagated through invocation chain

**TestErrorHandling:**
- Discovery failures logged but don't crash
- Missing user_id raises clear error

## Running Tests

### Run All MCP Tests
```bash
pytest tests/mcp/
```

### Run Specific Test File
```bash
pytest tests/mcp/test_mcp_client.py
pytest tests/mcp/test_mcp_plugin_registry.py
pytest tests/mcp/test_handler_integration.py
```

### Run Specific Test Class
```bash
pytest tests/mcp/test_mcp_client.py::TestAuthHeaderResolution
```

### Run with Coverage
```bash
pytest tests/mcp/ --cov=sk_agents.mcp_client --cov=sk_agents.mcp_plugin_registry --cov-report=html
```

## Key Testing Principles

### 1. **No Real OAuth2 Flows**
All OAuth2 testing uses pre-created `OAuth2AuthData` fixtures. No actual OAuth2 servers are contacted.

### 2. **No Real MCP Servers**
All MCP SDK components (`ClientSession`, `Tool`, etc.) are mocked using `AsyncMock` and `MagicMock`.

### 3. **Realistic Mock Behavior**
Mocks simulate real behavior:
- Token expiration checking
- Scope sorting and normalization
- Header filtering and security

### 4. **Defense-in-Depth Testing**
Tests verify multiple layers of security:
- Config validation (Pydantic models)
- Runtime filtering (static auth headers blocked)
- Governance application (annotations → trust → overrides)

### 5. **Per-User Context**
Tests verify user_id propagation throughout:
- Discovery uses user_id for initial token resolution
- Plugin instantiation requires user_id
- Tool invocation resolves per-user tokens

## Fixture Patterns

### Pattern 1: Simple Fixture Return
```python
@pytest.fixture
def mock_oauth2_token():
    return OAuth2AuthData(...)
```

### Pattern 2: Mock with Side Effects
```python
@pytest.fixture
def mock_auth_storage(mock_oauth2_token):
    storage = MagicMock()
    _storage = {"test_user": {"key": mock_oauth2_token}}
    storage.retrieve = Mock(side_effect=lambda uid, key: _storage.get(uid, {}).get(key))
    return storage
```

### Pattern 3: Async Mock
```python
@pytest.fixture
def mock_mcp_session():
    session = AsyncMock(spec=ClientSession)
    session.list_tools = AsyncMock(return_value=MagicMock(tools=[...]))
    return session
```

### Pattern 4: Patch Decorator
```python
@patch("sk_agents.mcp_client.AuthStorageFactory")
def test_something(self, mock_factory):
    # mock_factory is automatically injected
    mock_factory.return_value.get_auth_storage_manager.return_value = ...
```

## Common Test Scenarios

### Testing OAuth2 Token Resolution
```python
@patch("sk_agents.mcp_client.AuthStorageFactory")
def test_token_resolution(self, mock_factory, mock_oauth2_token):
    # Setup
    mock_storage = MagicMock()
    mock_storage.retrieve.return_value = mock_oauth2_token
    mock_factory.return_value.get_auth_storage_manager.return_value = mock_storage

    # Execute
    headers = resolve_server_auth_headers(config, "test_user")

    # Verify
    assert headers["Authorization"] == "Bearer mock_access_token_12345"
```

### Testing Governance Application
```python
def test_governance_with_overrides(self):
    base = Governance(requires_hitl=True, cost="high", data_sensitivity="sensitive")
    overrides = {"tool": GovernanceOverride(requires_hitl=False, cost="low")}

    result = apply_governance_overrides(base, "tool", overrides)

    assert result.requires_hitl is False  # Overridden
    assert result.cost == "low"  # Overridden
    assert result.data_sensitivity == "sensitive"  # Kept from base
```

### Testing MCP Discovery
```python
@pytest.mark.asyncio
@patch("sk_agents.mcp_plugin_registry.create_mcp_session")
async def test_discovery(self, mock_create_session, mock_mcp_session):
    mock_create_session.return_value = mock_mcp_session

    await McpPluginRegistry.discover_and_materialize([config], "test_user")

    plugin_class = McpPluginRegistry.get_plugin_class("server-name")
    assert plugin_class is not None
```

## Troubleshooting

### Issue: "AuthStorageFactory not mocked"
**Solution:** Add `@patch("sk_agents.mcp_client.AuthStorageFactory")` to test method.

### Issue: "AsyncMock not working"
**Solution:** Mark test with `@pytest.mark.asyncio` and use `async def test_...`

### Issue: "Mock not called"
**Solution:** Check that you're testing the right code path. Use `assert_called_once()` to verify.

### Issue: "Registry has stale data"
**Solution:** Use `cleanup_mcp_registry` fixture (auto-cleanup) or call `McpPluginRegistry.clear()` manually.

## Adding New Tests

### 1. Add Fixture to `conftest.py` (if needed)
```python
@pytest.fixture
def my_custom_fixture():
    return SomeObject(...)
```

### 2. Create Test Class
```python
class TestMyFeature:
    """Test my feature."""

    def test_basic_behavior(self, my_custom_fixture):
        # Arrange
        # Act
        # Assert
        pass
```

### 3. Use Appropriate Mocks
- OAuth2: Use `mock_oauth2_token`, `mock_auth_storage`
- MCP SDK: Use `mock_mcp_session`, `mock_mcp_tool`
- Configs: Use `http_mcp_config`, `stdio_mcp_config`, `github_mcp_config`

### 4. Mark Async Tests
```python
@pytest.mark.asyncio
async def test_async_operation(self):
    result = await some_async_function()
    assert result == expected
```

## Coverage Goals

Current coverage areas:
- ✅ Auth storage key building
- ✅ OAuth2 token resolution
- ✅ Governance mapping and overrides
- ✅ Trust level application
- ✅ Plugin class creation
- ✅ Tool catalog registration
- ✅ Discovery flow
- ✅ Handler integration
- ✅ User ID propagation

**Target:** 90%+ coverage for mcp_client.py and mcp_plugin_registry.py

## Further Reading

- **MCP Specification**: `docs/mcp-client-specification.md`
- **MCP Integration Guide**: `docs/mcp-integration.md`
- **Auth Storage Tests**: `tests/auth_storage/` (similar mocking patterns)
- **Pytest Fixtures**: https://docs.pytest.org/en/stable/fixture.html
- **unittest.mock**: https://docs.python.org/3/library/unittest.mock.html
