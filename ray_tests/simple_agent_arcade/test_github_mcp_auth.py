#!/usr/bin/env python3
"""
Test script for GitHub MCP OAuth2 authentication and auth-first discovery.

This script tests the complete flow:
1. Request without auth → AuthChallengeResponse
2. Token storage (manual or programmatic)
3. Request with auth → Discovery succeeds

Usage:
    python test_github_mcp_auth.py [--clear-auth] [--agent-url URL]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# Add sk-agents to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
SK_AGENTS_SRC = PROJECT_ROOT / "src" / "sk-agents" / "src"
sys.path.insert(0, str(SK_AGENTS_SRC))

SHARED_SRC = PROJECT_ROOT / "shared" / "ska_utils" / "src"
sys.path.insert(0, str(SHARED_SRC))

from ska_utils import AppConfig
from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.models import OAuth2AuthData


# Configuration
DEFAULT_AGENT_URL = "http://localhost:8000/FileAssistant/0.1/invoke"
USER_ID = "test_user"
GITHUB_AUTH_SERVER = "https://github.com/login/oauth"
GITHUB_SCOPES = ["repo", "read:packages", "read:org"]


def build_auth_storage_key(auth_server: str, scopes: list) -> str:
    """Build composite key for AuthStorage (matches mcp_client.py logic)."""
    normalized_scopes = '|'.join(sorted(scopes)) if scopes else ''
    return f"{auth_server}|{normalized_scopes}" if normalized_scopes else auth_server


def get_auth_storage():
    """Get AuthStorage instance."""
    app_config = AppConfig()
    factory = AuthStorageFactory(app_config)
    return factory.get_auth_storage_manager()


def clear_github_token():
    """Clear GitHub token from AuthStorage."""
    auth_storage = get_auth_storage()
    composite_key = build_auth_storage_key(GITHUB_AUTH_SERVER, GITHUB_SCOPES)

    try:
        auth_storage.delete(USER_ID, composite_key)
        print(f"✓ Cleared GitHub token from AuthStorage")
        print(f"  User ID: {USER_ID}")
        print(f"  Key: {composite_key}")
    except Exception as e:
        print(f"✗ Failed to clear token: {e}")


def check_github_token():
    """Check if GitHub token exists in AuthStorage."""
    auth_storage = get_auth_storage()
    composite_key = build_auth_storage_key(GITHUB_AUTH_SERVER, GITHUB_SCOPES)

    auth_data = auth_storage.retrieve(USER_ID, composite_key)

    if auth_data:
        print(f"✓ GitHub token found in AuthStorage")
        print(f"  User ID: {USER_ID}")
        print(f"  Key: {composite_key}")
        print(f"  Expires: {auth_data.expires_at}")
        print(f"  Scopes: {auth_data.scopes}")

        # Check if expired
        if auth_data.expires_at <= datetime.now(timezone.utc):
            print(f"  ⚠️  Token is EXPIRED")
            return False
        else:
            print(f"  ✓ Token is valid")
            return True
    else:
        print(f"✗ No GitHub token found in AuthStorage")
        print(f"  User ID: {USER_ID}")
        print(f"  Key: {composite_key}")
        return False


def test_request_without_auth(agent_url: str):
    """Test 1: Send request without auth, expect AuthChallengeResponse."""
    print("\n" + "=" * 70)
    print("TEST 1: Request without GitHub auth (expect AuthChallengeResponse)")
    print("=" * 70)

    payload = {
        "items": [{
            "content_type": "text",
            "content": "List my GitHub repositories"
        }]
    }

    try:
        response = requests.post(
            agent_url,
            json=payload,
            headers={"Authorization": "Bearer dummy"}
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            if "auth_challenges" in data:
                print("✓ Received AuthChallengeResponse as expected")
                print(f"\nMessage: {data.get('message')}")
                print(f"\nAuth Challenges:")
                for challenge in data["auth_challenges"]:
                    print(f"  Server: {challenge['server_name']}")
                    print(f"  Auth Server: {challenge['auth_server']}")
                    print(f"  Scopes: {challenge['scopes']}")
                    print(f"  Auth URL: {challenge['auth_url']}")
                print(f"\nResume URL: {data.get('resume_url')}")
                return True
            else:
                print("✗ Did not receive AuthChallengeResponse")
                print("  Possible causes:")
                print("  - Token already exists in AuthStorage (clear with --clear-auth)")
                print("  - MCP server not configured in config.yaml")
                print(f"\nResponse:")
                print(json.dumps(data, indent=2))
                return False
        else:
            print(f"✗ Unexpected status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"✗ Request failed: {e}")
        return False


def test_request_with_auth(agent_url: str):
    """Test 2: Send request with auth, expect normal response."""
    print("\n" + "=" * 70)
    print("TEST 2: Request with GitHub auth (expect normal response)")
    print("=" * 70)

    # First check if token exists
    if not check_github_token():
        print("\n⚠️  Cannot run test: No valid GitHub token in AuthStorage")
        print("   Complete OAuth2 flow first:")
        print("   1. Visit http://localhost:9000")
        print("   2. Click 'Authorize with GitHub'")
        print("   3. Complete authorization")
        return False

    payload = {
        "items": [{
            "content_type": "text",
            "content": "Search for repositories about MCP"
        }]
    }

    try:
        print("\nSending request to agent...")
        response = requests.post(
            agent_url,
            json=payload,
            headers={"Authorization": "Bearer dummy"}
        )

        print(f"Status Code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()

            if "auth_challenges" in data:
                print("✗ Still receiving AuthChallengeResponse")
                print("  Possible causes:")
                print("  - Token not found by discovery (check composite key)")
                print("  - Token expired")
                print("  - Discovery not using correct user_id")
                print(f"\nResponse:")
                print(json.dumps(data, indent=2))
                return False
            else:
                print("✓ Received normal response (not auth challenge)")
                print("✓ Discovery succeeded with GitHub auth!")
                print(f"\nResponse preview:")
                output = data.get("output", "")
                print(output[:500] + "..." if len(output) > 500 else output)
                return True
        else:
            print(f"✗ Unexpected status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"✗ Request failed: {e}")
        return False


def manual_token_entry():
    """Manually enter GitHub token for testing."""
    print("\n" + "=" * 70)
    print("MANUAL TOKEN ENTRY")
    print("=" * 70)
    print("\nThis will store a GitHub token in AuthStorage for testing.")
    print("You can get a GitHub Personal Access Token from:")
    print("  https://github.com/settings/tokens")
    print("\nRequired scopes: repo, read:packages, read:org")
    print()

    token = input("Enter GitHub token (or press Enter to skip): ").strip()

    if not token:
        print("Skipped")
        return

    try:
        auth_storage = get_auth_storage()
        composite_key = build_auth_storage_key(GITHUB_AUTH_SERVER, GITHUB_SCOPES)

        auth_data = OAuth2AuthData(
            access_token=token,
            expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            scopes=GITHUB_SCOPES
        )

        auth_storage.store(USER_ID, composite_key, auth_data)

        print(f"\n✓ Token stored successfully")
        print(f"  User ID: {USER_ID}")
        print(f"  Key: {composite_key}")
        print(f"  Expires: {auth_data.expires_at}")

    except Exception as e:
        print(f"\n✗ Failed to store token: {e}")


def main():
    parser = argparse.ArgumentParser(description="Test GitHub MCP OAuth2 auth flow")
    parser.add_argument("--clear-auth", action="store_true", help="Clear GitHub token from AuthStorage")
    parser.add_argument("--check-auth", action="store_true", help="Check if GitHub token exists")
    parser.add_argument("--agent-url", default=DEFAULT_AGENT_URL, help="Agent URL")
    parser.add_argument("--manual-token", action="store_true", help="Manually enter token")
    parser.add_argument("--test-without-auth", action="store_true", help="Only test without auth")
    parser.add_argument("--test-with-auth", action="store_true", help="Only test with auth")

    args = parser.parse_args()

    print("=" * 70)
    print("  GitHub MCP OAuth2 Auth Testing")
    print("=" * 70)
    print(f"\nAgent URL: {args.agent_url}")
    print(f"User ID: {USER_ID}")
    print(f"GitHub Auth Server: {GITHUB_AUTH_SERVER}")
    print(f"GitHub Scopes: {GITHUB_SCOPES}")

    if args.clear_auth:
        print()
        clear_github_token()
        return

    if args.check_auth:
        print()
        check_github_token()
        return

    if args.manual_token:
        manual_token_entry()
        return

    # Run tests
    results = []

    if not args.test_with_auth:
        # Test 1: Without auth
        results.append(("Request without auth", test_request_without_auth(args.agent_url)))

    if not args.test_without_auth:
        # Test 2: With auth
        results.append(("Request with auth", test_request_with_auth(args.agent_url)))

    # Summary
    print("\n" + "=" * 70)
    print("  TEST SUMMARY")
    print("=" * 70)
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print("\n" + "=" * 70)

    # Exit code
    if all(result for _, result in results):
        print("All tests passed!")
        sys.exit(0)
    else:
        print("Some tests failed. See above for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
