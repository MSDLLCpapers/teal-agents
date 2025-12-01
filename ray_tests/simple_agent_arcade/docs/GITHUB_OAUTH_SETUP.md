# GitHub OAuth2 Setup for MCP Testing

> **⚠️ TEST INFRASTRUCTURE NOTICE**
>
> This is a **test harness** for validating auth-first MCP discovery. It uses a standalone OAuth2 server (`github_oauth_handler.py`) on port 9001 to simulate OAuth flows.
>
> **This is NOT production architecture.** The Teal Agents platform is designed to have centralized OAuth endpoints (see `src/sk-agents/docs/planning/2507-state-hitl-auth/05-01-auth-infra-overview.md`), but those endpoints are not yet implemented.
>
> **What This Tests:**
> - ✅ Auth-first discovery (pre-flight auth validation)
> - ✅ AuthChallengeResponse when auth is missing
> - ✅ Token storage and retrieval via AuthStorage
> - ✅ Successful MCP discovery with authentication
>
> **Production Architecture (Future):**
> Platform-level OAuth endpoints at `/oauth/{provider}/authorize` and `/oauth/{provider}/callback` that serve all agents centrally.

---

This guide walks you through testing the **auth-first discovery** implementation with the real GitHub MCP server using a complete OAuth2 flow.

## What You'll Test

✅ Auth-first discovery - Pre-flight auth check before MCP tool discovery
✅ AuthChallengeResponse - Proper error handling when auth missing
✅ Real GitHub OAuth2 flow - Complete authorization code flow
✅ AuthStorage integration - Token storage and retrieval
✅ Bearer token authentication - HTTP Authorization headers
✅ GitHub MCP tools - Real tool discovery and invocation

---

## Prerequisites

- Python 3.11+
- GitHub account
- Agent environment set up (see main README.md)
- **Redis server** (for cross-process token sharing)

---

## Step 0: Start Redis Server

**Why Redis?** The OAuth handler (port 9001) and agent (port 8000) are **separate processes**. They cannot share in-memory tokens. Redis provides cross-process AuthStorage.

**Option A - Local Redis:**
```bash
# Install Redis (if not already installed)
# macOS: brew install redis
# Ubuntu: sudo apt-get install redis-server

# Start Redis
redis-server
```

**Option B - Docker Redis:**
```bash
docker run -d -p 6379:6379 --name redis-auth redis
```

**Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

Keep Redis running throughout the testing session.

---

## Step 1: Create GitHub OAuth App

1. Go to: https://github.com/settings/developers
2. Click **"New OAuth App"**
3. Fill in the form:
   - **Application name**: `Teal Agents MCP Test` (or any name)
   - **Homepage URL**: `http://localhost:8000`
   - **Authorization callback URL**: `http://localhost:9001/oauth/github/callback`
4. Click **"Register application"**
5. On the app page, note your **Client ID**
6. Click **"Generate a new client secret"** and note the **Client Secret**

**Important**: Keep your Client Secret secure! Don't commit it to git.

---

## Step 2: Configure Environment

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` and add your **Client Secret** (keep Client ID for Step 3):
```bash
# GitHub OAuth2 Configuration for MCP Testing
GITHUB_OAUTH_CLIENT_SECRET=your_client_secret_from_step_1
GITHUB_OAUTH_REDIRECT_URI=http://localhost:9001/oauth/github/callback

# Redis AuthStorage (already configured in .env.example)
TA_AUTH_STORAGE_MANAGER_MODULE=/path/to/example_redis_auth_storage.py
TA_AUTH_STORAGE_MANAGER_CLASS=RedisSecureAuthStorageManager
TA_REDIS_HOST=localhost
TA_REDIS_PORT=6379
TA_REDIS_DB=0
TA_REDIS_TTL=3600
```

**Notes:**
- Client ID will be prompted for interactively in Step 3
- Redis configuration is **required** for cross-process token sharing
- This simulates production architecture where:
  - **Platform stores secrets** (CLIENT_SECRET in secure environment config)
  - **Users provide OAuth app details** (CLIENT_ID at runtime)

---

## Step 3: Start OAuth2 Server

In **Terminal 1**, start the OAuth2 handler:
```bash
cd ray_tests/simple_agent_1
python github_oauth_handler.py
```

You'll be prompted to enter your **Client ID**:
```
======================================================================
  GitHub OAuth2 Handler for MCP Testing
======================================================================

======================================================================
  GitHub OAuth2 Configuration
======================================================================

The OAuth client secret is configured via environment (.env file).
Please provide your GitHub OAuth App Client ID below.

To find your Client ID:
  1. Visit: https://github.com/settings/developers
  2. Open your OAuth App
  3. Copy the 'Client ID' value

Enter GitHub OAuth Client ID: <paste your client ID here>

✅ Configuration complete!
   Client ID: Ov23li...
   Redirect URI: http://localhost:9001/oauth/github/callback

======================================================================
Starting OAuth2 server on http://localhost:9001

To authenticate:
  1. Visit http://localhost:9001
  2. Click 'Authorize with GitHub'
  3. Complete GitHub authorization
======================================================================
```

Keep this terminal running.

---

## Step 4: Start Agent

In **Terminal 2**, start the agent:
```bash
cd ray_tests/simple_agent_1
python run_agent.py
```

You should see:
```
======================================================================
  FileAssistant Test Agent - Standalone Runner
======================================================================

Starting FastAPI Server
...
Agent will be available at:
  - API Endpoint: http://localhost:8000/FileAssistant/0.1/invoke
  - Swagger UI: http://localhost:8000/FileAssistant/0.1/docs
======================================================================
```

Keep this terminal running.

---

## Step 5: Test Auth-First Discovery (No Auth)

In **Terminal 3**, send a request to the agent **without** GitHub authentication:

```bash
curl -X POST http://localhost:8000/FileAssistant/0.1/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "items": [{
      "content_type": "text",
      "content": "List my GitHub repositories"
    }]
  }'
```

**Expected Result**: `AuthChallengeResponse`

```json
{
  "task_id": "...",
  "session_id": "...",
  "request_id": "...",
  "message": "Authentication required for MCP server 'github-copilot' before tool discovery",
  "auth_challenges": [{
    "server_name": "github-copilot",
    "auth_server": "https://github.com/login/oauth",
    "scopes": ["repo", "read:packages", "read:org"],
    "auth_url": "http://localhost:9001/oauth/github/authorize?user_id=test_user"
  }],
  "resume_url": "/tealagents/v1alpha1/invoke"
}
```

**What Happened**:
1. Agent attempted MCP discovery
2. `_discover_server()` called for `github-copilot`
3. **Pre-flight auth check**: Checked AuthStorage for token
4. **No token found** ❌
5. Raised `AuthRequiredError`
6. Handler returned `AuthChallengeResponse`

---

## Step 6: Complete OAuth2 Flow

Copy the `auth_url` from the response and open it in your browser:
```
http://localhost:9001/oauth/github/authorize?user_id=test_user
```

You'll be redirected to GitHub. The flow:
1. **OAuth2 Server**: Generates CSRF token, redirects to GitHub
2. **GitHub**: Shows authorization page for your app
3. **You**: Click "Authorize {your-app-name}"
4. **GitHub**: Redirects back to callback with authorization code
5. **OAuth2 Server**: Exchanges code for access token
6. **OAuth2 Server**: Stores token in AuthStorage
7. **Browser**: Shows success page

**Success Page**:
```
✓ GitHub Authorization Successful

Your GitHub access token has been stored successfully.

User ID: test_user
Scopes: repo, read:packages, read:org
Storage Key: https://github.com/login/oauth|read:org|read:packages|repo

Next Steps:
1. Close this window
2. Return to your agent chat/terminal
3. Send a request to your agent
4. MCP tools from GitHub will now be discovered automatically!
```

---

## Step 7: Test Discovery with Auth

In **Terminal 3**, send the same request again:

```bash
curl -X POST http://localhost:8000/FileAssistant/0.1/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "items": [{
      "content_type": "text",
      "content": "List my GitHub repositories"
    }]
  }'
```

**Expected Result**: Agent processes the request (NOT `AuthChallengeResponse`)

**What Happened**:
1. Agent attempted MCP discovery
2. `_discover_server()` called for `github-copilot`
3. **Pre-flight auth check**: Checked AuthStorage for token
4. **Token found** ✅
5. **Token not expired** ✅
6. Proceeded with discovery:
   - Created MCP session with Bearer token
   - Called `session.list_tools()` with `Authorization: Bearer {token}` header
   - GitHub MCP server returned tool list
   - Tools registered in plugin catalog
7. Discovery marked as complete
8. Agent construction proceeded
9. LLM selected GitHub tools and invoked them!

---

## Step 8: Test GitHub MCP Tools

Now that GitHub MCP tools are discovered, you can use them:

```bash
curl -X POST http://localhost:8000/FileAssistant/0.1/invoke \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "items": [{
      "content_type": "text",
      "content": "Search for repositories about MCP"
    }]
  }'
```

The agent will use GitHub MCP tools like:
- `github_copilot_search_repositories`
- `github_copilot_list_repositories`
- `github_copilot_get_file_contents`
- etc.

---

## Verification Checklist

After completing the flow, verify:

- [ ] **AuthChallengeResponse returned** when no token present
- [ ] **OAuth2 flow completed** successfully
- [ ] **Token stored in AuthStorage** with correct composite key
- [ ] **Discovery succeeded** on retry with token
- [ ] **GitHub MCP tools discovered** and registered
- [ ] **Tools invoked successfully** with Bearer token

---

## Troubleshooting

### Issue: "GITHUB_OAUTH_CLIENT_ID not configured"

**Solution**: Check your `.env` file has the correct Client ID from Step 1.

### Issue: "Invalid state" during callback

**Solution**: CSRF token mismatch. Start fresh - close browser, restart OAuth2 server, try again.

### Issue: "Token exchange failed"

**Solution**:
- Verify Client Secret is correct in `.env`
- Check GitHub OAuth App callback URL matches exactly: `http://localhost:9001/oauth/github/callback`

### Issue: Discovery still fails after auth

**Solution**:
- Check AuthStorage has token: Run test script to inspect AuthStorage
- Verify composite key matches: Should be `https://github.com/login/oauth|read:org|read:packages|repo` (scopes sorted alphabetically)

### Issue: GitHub MCP server returns 401

**Solution**:
- Token may be invalid or expired
- Try refreshing by completing OAuth2 flow again

---

## Understanding the Flow

### Discovery Phase Components

```
_ensure_mcp_discovery(user_id, session_id, task_id, request_id)
  ↓
_discover_server(server_config, user_id)
  ↓
Pre-flight Auth Check:
  if server_config.auth_server and server_config.scopes:
    composite_key = build_auth_storage_key(auth_server, scopes)
    auth_data = auth_storage.retrieve(user_id, composite_key)
    if not auth_data:
      raise AuthRequiredError(...)  ← Returns AuthChallengeResponse
  ↓
create_mcp_session(server_config, stack, user_id)
  ↓
resolve_server_auth_headers(server_config, user_id)
  ↓
session.list_tools()  ← Called with Bearer token
  ↓
Tools discovered and registered
```

### Key Files Modified

| File | What Changed |
|------|--------------|
| `mcp_client.py:37-49` | Added `AuthRequiredError` exception |
| `mcp_plugin_registry.py:105-144` | Added pre-flight auth validation |
| `mcp_plugin_registry.py:91-117` | Propagate auth errors to handler |
| `handler.py:69-127` | Return `AuthChallengeResponse` from discovery |
| `handler.py:539-566` | Check discovery auth challenge in `invoke()` |
| `handler.py:586-613` | Check discovery auth challenge in `invoke_stream()` |

---

## Next Steps

After successful testing:

1. **Document findings** - Note any issues or improvements
2. **Test other scenarios** - Expired tokens, invalid scopes, etc.
3. **Test with other MCP servers** - Apply same pattern to other services
4. **Production deployment** - Consider using Redis for CSRF tokens, secure token storage, etc.

---

## Resources

- **GitHub MCP Server**: https://github.com/github/github-mcp-server
- **MCP Specification**: https://modelcontextprotocol.io/
- **GitHub OAuth2 Docs**: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps
- **Teal Agents MCP Docs**: `../../src/sk-agents/docs/mcp-integration.md`
