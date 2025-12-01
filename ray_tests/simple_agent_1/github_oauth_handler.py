"""
GitHub OAuth2 Handler for MCP Testing

This module provides OAuth2 endpoints for authenticating with GitHub
and storing tokens in AuthStorage for MCP server access.
"""

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

# Load .env file from the same directory as this script
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# OAuth2 configuration from environment
# Note: CLIENT_ID will be prompted for interactively to simulate production
# where platform stores secrets but users provide their OAuth app details
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "")
GITHUB_OAUTH_REDIRECT_URI = os.getenv("GITHUB_OAUTH_REDIRECT_URI", "http://localhost:9001/oauth/github/callback")

# Required scopes for GitHub MCP server
GITHUB_SCOPES = ["repo", "read:packages", "read:org"]

# In-memory CSRF token storage (use Redis in production)
csrf_tokens: Dict[str, bool] = {}

# Global to store client ID (set at startup)
GITHUB_CLIENT_ID: str = ""

app = FastAPI(title="GitHub OAuth2 Handler for MCP")


def get_auth_storage():
    """Get AuthStorage instance."""
    import sys
    from pathlib import Path

    # Add sk-agents to path
    project_root = Path(__file__).parent.parent.parent
    sk_agents_src = project_root / "src" / "sk-agents" / "src"
    sys.path.insert(0, str(sk_agents_src))

    from ska_utils import AppConfig
    from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory

    app_config = AppConfig()
    factory = AuthStorageFactory(app_config)
    return factory.get_auth_storage_manager()


def build_auth_storage_key(auth_server: str, scopes: list[str]) -> str:
    """Build composite key for AuthStorage (must match mcp_client.py logic)."""
    normalized_scopes = '|'.join(sorted(scopes)) if scopes else ''
    return f"{auth_server}|{normalized_scopes}" if normalized_scopes else auth_server


@app.get("/")
async def root():
    """Root endpoint with instructions."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>GitHub OAuth2 for MCP</title>
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
            .button { display: inline-block; padding: 10px 20px; background: #0366d6; color: white;
                     text-decoration: none; border-radius: 5px; }
            .code { background: #f6f8fa; padding: 2px 5px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <h1>GitHub OAuth2 Handler for MCP Testing</h1>
        <p>This server handles OAuth2 authentication for the GitHub MCP server.</p>

        <h2>Setup Steps</h2>
        <ol>
            <li>Create a GitHub OAuth App at <a href="https://github.com/settings/developers">https://github.com/settings/developers</a></li>
            <li>Set callback URL to: <span class="code">http://localhost:9000/oauth/github/callback</span></li>
            <li>Configure environment variables in <span class="code">.env</span></li>
            <li>Click the button below to start authentication</li>
        </ol>

        <h2>Authenticate</h2>
        <a href="/oauth/github/authorize" class="button">Authorize with GitHub</a>

        <h2>Status</h2>
        <p>Client ID configured: <strong>{}</strong></p>
        <p>Redirect URI: <span class="code">{}</span></p>
    </body>
    </html>
    """.format(
        "✓ Yes" if GITHUB_CLIENT_ID else "✗ No (check .env)",
        GITHUB_OAUTH_REDIRECT_URI
    )
    return HTMLResponse(html_content)


@app.get("/oauth/github/authorize")
async def github_authorize(user_id: str = Query(default="test_user")):
    """
    Initiate GitHub OAuth2 flow.

    Args:
        user_id: User ID for AuthStorage (defaults to "test_user")
    """
    if not GITHUB_CLIENT_ID:
        raise HTTPException(status_code=500, detail="GITHUB_OAUTH_CLIENT_ID not configured")

    # Generate CSRF token
    state = secrets.token_urlsafe(32)
    csrf_tokens[state] = user_id  # Store user_id with state

    # Build GitHub OAuth2 authorization URL
    scope_string = ",".join(GITHUB_SCOPES)
    auth_url = (
        f"https://github.com/login/oauth/authorize"
        f"?client_id={GITHUB_CLIENT_ID}"
        f"&redirect_uri={GITHUB_OAUTH_REDIRECT_URI}"
        f"&scope={scope_string}"
        f"&state={state}"
    )

    print(f"[OAuth2] Redirecting user '{user_id}' to GitHub for authorization")
    return RedirectResponse(auth_url)


@app.get("/oauth/github/callback")
async def github_callback(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(..., description="CSRF token")
):
    """
    Handle GitHub OAuth2 callback.

    Exchanges authorization code for access token and stores in AuthStorage.
    """
    # Verify CSRF token
    if state not in csrf_tokens:
        return HTMLResponse(
            "<h1>Error: Invalid State</h1><p>CSRF token validation failed</p>",
            status_code=400
        )

    user_id = csrf_tokens.pop(state)

    try:
        # Exchange authorization code for access token
        print(f"[OAuth2] Exchanging authorization code for access token")
        token_response = requests.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": GITHUB_CLIENT_ID,
                "client_secret": GITHUB_CLIENT_SECRET,
                "code": code,
                "redirect_uri": GITHUB_OAUTH_REDIRECT_URI
            },
            headers={"Accept": "application/json"}
        )

        if token_response.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Token exchange failed: {token_response.text}")

        token_data = token_response.json()

        if "error" in token_data:
            raise HTTPException(status_code=500, detail=f"GitHub error: {token_data['error_description']}")

        access_token = token_data["access_token"]
        scope_string = token_data.get("scope", "")
        granted_scopes = scope_string.split(",") if scope_string else GITHUB_SCOPES

        print(f"[OAuth2] Access token received (scopes: {granted_scopes})")

        # Store token in AuthStorage
        from sk_agents.auth_storage.models import OAuth2AuthData

        auth_storage = get_auth_storage()

        # Build composite key matching MCP config
        composite_key = build_auth_storage_key(
            "https://github.com/login/oauth",
            granted_scopes
        )

        # Create OAuth2AuthData
        oauth_data = OAuth2AuthData(
            access_token=access_token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),  # GitHub PATs don't expire
            scopes=granted_scopes
        )

        # Store in AuthStorage
        auth_storage.store(user_id, composite_key, oauth_data)

        print(f"[OAuth2] Token stored successfully for user '{user_id}' with key '{composite_key}'")

        # Return success page
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Successful</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
                .success {{ color: #28a745; }}
                .code {{ background: #f6f8fa; padding: 2px 5px; border-radius: 3px; }}
                .info {{ background: #f6f8fa; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <h1 class="success">✓ GitHub Authorization Successful</h1>
            <p>Your GitHub access token has been stored successfully.</p>

            <div class="info">
                <strong>User ID:</strong> <span class="code">{user_id}</span><br>
                <strong>Scopes:</strong> <span class="code">{', '.join(granted_scopes)}</span><br>
                <strong>Storage Key:</strong> <span class="code">{composite_key}</span>
            </div>

            <h2>Next Steps</h2>
            <ol>
                <li>Close this window</li>
                <li>Return to your agent chat/terminal</li>
                <li>Send a request to your agent</li>
                <li>MCP tools from GitHub will now be discovered automatically!</li>
            </ol>

            <h2>What Happened?</h2>
            <p>Your GitHub access token is now stored in AuthStorage. When the agent attempts
            MCP discovery, it will:</p>
            <ol>
                <li>Check AuthStorage for your GitHub token ✓</li>
                <li>Find the token and validate it's not expired ✓</li>
                <li>Proceed with discovery, using the token in Authorization header ✓</li>
                <li>Discover GitHub MCP tools and register them ✓</li>
            </ol>
        </body>
        </html>
        """

        return HTMLResponse(success_html)

    except Exception as e:
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Authorization Failed</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }}
                .error {{ color: #d73a49; }}
            </style>
        </head>
        <body>
            <h1 class="error">✗ Authorization Failed</h1>
            <p>An error occurred during the OAuth2 flow:</p>
            <pre>{str(e)}</pre>
            <p><a href="/">Try again</a></p>
        </body>
        </html>
        """
        return HTMLResponse(error_html, status_code=500)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "oauth_configured": bool(GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET),
        "redirect_uri": GITHUB_OAUTH_REDIRECT_URI
    }


def prompt_for_client_id() -> str:
    """
    Prompt user for GitHub OAuth Client ID.

    This simulates production architecture where the platform stores secrets
    securely but users provide their OAuth app client IDs at runtime.
    """
    print("\n" + "=" * 70)
    print("  GitHub OAuth2 Configuration")
    print("=" * 70)
    print()
    print("The OAuth client secret is configured via environment (.env file).")
    print("Please provide your GitHub OAuth App Client ID below.")
    print()
    print("To find your Client ID:")
    print("  1. Visit: https://github.com/settings/developers")
    print("  2. Open your OAuth App")
    print("  3. Copy the 'Client ID' value")
    print()

    while True:
        client_id = input("Enter GitHub OAuth Client ID: ").strip()
        if client_id:
            return client_id
        print("❌ Client ID cannot be empty. Please try again.\n")


if __name__ == "__main__":
    import uvicorn

    print("=" * 70)
    print("  GitHub OAuth2 Handler for MCP Testing")
    print("=" * 70)

    # Check if client secret is configured
    if not GITHUB_CLIENT_SECRET:
        print("\n❌ ERROR: GITHUB_OAUTH_CLIENT_SECRET not configured in .env")
        print("\nPlease:")
        print("  1. Copy .env.example to .env")
        print("  2. Add your GitHub OAuth App Client Secret")
        print("  3. Restart this server")
        exit(1)

    # Prompt for client ID (simulates user providing OAuth app details)
    GITHUB_CLIENT_ID = prompt_for_client_id()

    print("\n✅ Configuration complete!")
    print(f"   Client ID: {GITHUB_CLIENT_ID}")
    print(f"   Redirect URI: {GITHUB_OAUTH_REDIRECT_URI}")
    print()
    print("=" * 70)
    print("Starting OAuth2 server on http://localhost:9001")
    print()
    print("To authenticate:")
    print("  1. Visit http://localhost:9001")
    print("  2. Click 'Authorize with GitHub'")
    print("  3. Complete GitHub authorization")
    print("=" * 70)
    print()

    uvicorn.run(app, host="0.0.0.0", port=9001, log_level="info")
