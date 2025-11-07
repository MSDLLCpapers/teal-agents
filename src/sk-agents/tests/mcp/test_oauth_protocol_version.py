"""
Tests for MCP OAuth Protocol Version Detection

Verifies that resource parameter is conditionally included based on protocol version
per MCP specification 2025-06-18.
"""

import pytest
from sk_agents.auth.oauth_client import OAuthClient
from sk_agents.auth.oauth_models import AuthorizationRequest, TokenRequest


class TestProtocolVersionDetection:
    """Test protocol version-based resource parameter inclusion."""

    def test_should_include_resource_param_with_2025_06_18(self):
        """Resource param should be included for protocol version 2025-06-18."""
        result = OAuthClient.should_include_resource_param(protocol_version="2025-06-18")
        assert result is True

    def test_should_include_resource_param_with_newer_version(self):
        """Resource param should be included for versions after 2025-06-18."""
        result = OAuthClient.should_include_resource_param(protocol_version="2025-12-31")
        assert result is True

    def test_should_not_include_resource_param_with_older_version(self):
        """Resource param should not be included for versions before 2025-06-18."""
        result = OAuthClient.should_include_resource_param(protocol_version="2024-01-01")
        assert result is False

    def test_should_not_include_resource_param_with_no_version(self):
        """Resource param should not be included when protocol version is None."""
        result = OAuthClient.should_include_resource_param(protocol_version=None)
        assert result is False

    def test_should_include_resource_param_with_prm(self):
        """Resource param should be included when PRM is discovered, regardless of version."""
        result = OAuthClient.should_include_resource_param(
            protocol_version=None, has_prm=True
        )
        assert result is True

    def test_should_include_resource_param_with_prm_and_old_version(self):
        """PRM takes precedence over old protocol version."""
        result = OAuthClient.should_include_resource_param(
            protocol_version="2024-01-01", has_prm=True
        )
        assert result is True


class TestAuthorizationRequestWithProtocolVersion:
    """Test AuthorizationRequest with conditional resource parameter."""

    def test_authorization_request_with_resource(self):
        """Authorization request can include resource parameter."""
        request = AuthorizationRequest(
            auth_server="https://auth.example.com",
            client_id="test-client",
            redirect_uri="https://app.example.com/callback",
            resource="https://mcp.example.com",
            scopes=["read", "write"],
            state="random-state",
            code_challenge="challenge",
        )
        assert request.resource == "https://mcp.example.com"

    def test_authorization_request_without_resource(self):
        """Authorization request can omit resource parameter for backward compat."""
        request = AuthorizationRequest(
            auth_server="https://auth.example.com",
            client_id="test-client",
            redirect_uri="https://app.example.com/callback",
            resource=None,  # Omitted for older protocol
            scopes=["read", "write"],
            state="random-state",
            code_challenge="challenge",
        )
        assert request.resource is None

    def test_build_authorization_url_with_resource(self):
        """Authorization URL includes resource parameter when provided."""
        client = OAuthClient()
        request = AuthorizationRequest(
            auth_server="https://auth.example.com",
            client_id="test-client",
            redirect_uri="https://app.example.com/callback",
            resource="https://mcp.example.com",
            scopes=["read", "write"],
            state="test-state",
            code_challenge="test-challenge",
        )

        url = client.build_authorization_url(request)

        assert "resource=https%3A%2F%2Fmcp.example.com" in url
        assert "client_id=test-client" in url
        assert "state=test-state" in url

    def test_build_authorization_url_without_resource(self):
        """Authorization URL omits resource parameter when not provided."""
        client = OAuthClient()
        request = AuthorizationRequest(
            auth_server="https://auth.example.com",
            client_id="test-client",
            redirect_uri="https://app.example.com/callback",
            resource=None,  # Omitted
            scopes=["read", "write"],
            state="test-state",
            code_challenge="test-challenge",
        )

        url = client.build_authorization_url(request)

        assert "resource=" not in url
        assert "client_id=test-client" in url
        assert "state=test-state" in url


class TestTokenRequestWithProtocolVersion:
    """Test TokenRequest with conditional resource parameter."""

    def test_token_request_with_resource(self):
        """Token request can include resource parameter."""
        request = TokenRequest(
            token_endpoint="https://auth.example.com/token",
            grant_type="authorization_code",
            code="auth-code",
            redirect_uri="https://app.example.com/callback",
            code_verifier="verifier",
            resource="https://mcp.example.com",
            client_id="test-client",
        )
        assert request.resource == "https://mcp.example.com"

    def test_token_request_without_resource(self):
        """Token request can omit resource parameter for backward compat."""
        request = TokenRequest(
            token_endpoint="https://auth.example.com/token",
            grant_type="authorization_code",
            code="auth-code",
            redirect_uri="https://app.example.com/callback",
            code_verifier="verifier",
            resource=None,  # Omitted
            client_id="test-client",
        )
        assert request.resource is None


class TestProtocolVersionComparison:
    """Test protocol version string comparison."""

    def test_version_comparison_equal(self):
        """Version 2025-06-18 should be >= 2025-06-18."""
        assert "2025-06-18" >= "2025-06-18"

    def test_version_comparison_greater(self):
        """Newer versions should be > 2025-06-18."""
        assert "2025-12-31" >= "2025-06-18"
        assert "2026-01-01" >= "2025-06-18"

    def test_version_comparison_less(self):
        """Older versions should be < 2025-06-18."""
        assert not ("2024-01-01" >= "2025-06-18")
        assert not ("2025-01-01" >= "2025-06-18")
