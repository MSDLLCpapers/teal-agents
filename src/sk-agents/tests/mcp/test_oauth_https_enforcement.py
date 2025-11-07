"""
Tests for HTTPS Enforcement

Verifies HTTPS validation per OAuth 2.1 and MCP specification.
"""

import pytest
from unittest.mock import patch
from sk_agents.tealagents.v1alpha1.config import McpServerConfig
from sk_agents.mcp_client import validate_https_url


class TestValidateHttpsUrl:
    """Test validate_https_url function."""

    def test_validate_https_url_accepts_https(self):
        """HTTPS URLs should be valid."""
        assert validate_https_url("https://api.example.com") is True
        assert validate_https_url("https://example.com:8443/path") is True

    def test_validate_https_url_rejects_http(self):
        """HTTP URLs should be invalid (except localhost)."""
        assert validate_https_url("http://api.example.com") is False
        assert validate_https_url("http://example.com:8080/path") is False

    def test_validate_https_url_accepts_localhost_http(self):
        """HTTP localhost should be accepted for development."""
        assert validate_https_url("http://localhost", allow_localhost=True) is True
        assert validate_https_url("http://localhost:3000", allow_localhost=True) is True
        assert validate_https_url("http://127.0.0.1", allow_localhost=True) is True
        assert validate_https_url("http://127.0.0.1:8080", allow_localhost=True) is True

    def test_validate_https_url_rejects_localhost_when_disabled(self):
        """HTTP localhost should be rejected when allow_localhost=False."""
        assert validate_https_url("http://localhost", allow_localhost=False) is False
        assert validate_https_url("http://127.0.0.1", allow_localhost=False) is False

    def test_validate_https_url_accepts_localhost_https(self):
        """HTTPS localhost should always be accepted."""
        assert validate_https_url("https://localhost", allow_localhost=True) is True
        assert validate_https_url("https://127.0.0.1", allow_localhost=False) is True

    def test_validate_https_url_handles_ipv6_localhost(self):
        """IPv6 localhost should be accepted."""
        assert validate_https_url("http://[::1]", allow_localhost=True) is True
        assert validate_https_url("http://[::1]:8080", allow_localhost=True) is True

    def test_validate_https_url_rejects_malformed(self):
        """Malformed URLs should be rejected."""
        assert validate_https_url("not-a-url") is False
        assert validate_https_url("") is False


class TestMcpServerConfigHttpsEnforcement:
    """Test HTTPS enforcement in McpServerConfig validation."""

    @patch("ska_utils.AppConfig")
    def test_config_accepts_https_auth_server(self, mock_app_config):
        """Config should accept HTTPS auth_server when strict mode enabled."""
        # Mock feature flag and redirect URI
        mock_config_instance = mock_app_config.return_value
        mock_config_instance.get.side_effect = lambda key: (
            "true" if "STRICT_HTTPS" in key else "https://app.example.com/callback"
        )

        # Should not raise
        config = McpServerConfig(
            name="test-server",
            transport="http",
            url="https://mcp.example.com",
            auth_server="https://auth.example.com",
            scopes=["read", "write"],
        )
        assert config.auth_server == "https://auth.example.com"

    @patch("ska_utils.AppConfig")
    def test_config_rejects_http_auth_server(self, mock_app_config):
        """Config should reject HTTP auth_server when strict mode enabled."""
        # Mock feature flag
        mock_config_instance = mock_app_config.return_value
        mock_config_instance.get.side_effect = lambda key: (
            "true" if "STRICT_HTTPS" in key else "http://localhost:8000/oauth/callback"
        )

        # Should raise ValueError
        with pytest.raises(ValueError, match="auth_server must use HTTPS"):
            McpServerConfig(
                name="test-server",
                transport="http",
                url="https://mcp.example.com",
                auth_server="http://api.example.com",  # HTTP not allowed!
                scopes=["read", "write"],
            )

    @patch("ska_utils.AppConfig")
    def test_config_accepts_localhost_auth_server(self, mock_app_config):
        """Config should accept http://localhost auth_server in strict mode."""
        # Mock feature flag
        mock_config_instance = mock_app_config.return_value
        mock_config_instance.get.side_effect = lambda key: (
            "true" if "STRICT_HTTPS" in key else "http://localhost:8000/oauth/callback"
        )

        # Should not raise (localhost exception)
        config = McpServerConfig(
            name="test-server",
            transport="http",
            url="https://mcp.example.com",
            auth_server="http://localhost:3000",  # Localhost OK
            scopes=["read", "write"],
        )
        assert config.auth_server == "http://localhost:3000"

    @patch("ska_utils.AppConfig")
    def test_config_accepts_http_when_strict_disabled(self, mock_app_config):
        """Config should accept HTTP auth_server when strict mode disabled."""
        # Mock feature flag
        mock_config_instance = mock_app_config.return_value
        mock_config_instance.get.side_effect = lambda key: (
            "false" if "STRICT_HTTPS" in key else "http://localhost:8000/oauth/callback"
        )

        # Should not raise (strict mode disabled)
        config = McpServerConfig(
            name="test-server",
            transport="http",
            url="https://mcp.example.com",
            auth_server="http://api.example.com",  # HTTP OK when strict=false
            scopes=["read", "write"],
        )
        assert config.auth_server == "http://api.example.com"

    @patch("ska_utils.AppConfig")
    def test_config_validates_redirect_uri_https(self, mock_app_config):
        """Config should validate redirect_uri uses HTTPS when strict mode enabled."""
        # Mock feature flag and redirect URI
        mock_config_instance = mock_app_config.return_value
        mock_config_instance.get.side_effect = lambda key: {
            "TA_MCP_OAUTH_STRICT_HTTPS_VALIDATION": "true",
            "TA_OAUTH_REDIRECT_URI": "http://app.example.com/callback",  # HTTP not allowed!
        }.get(key, "default")

        # Should raise ValueError for HTTP redirect_uri
        with pytest.raises(ValueError, match="redirect_uri must use HTTPS"):
            McpServerConfig(
                name="test-server",
                transport="http",
                url="https://mcp.example.com",
                auth_server="https://auth.example.com",
                scopes=["read", "write"],
            )

    @patch("ska_utils.AppConfig")
    def test_config_accepts_localhost_redirect_uri(self, mock_app_config):
        """Config should accept http://localhost redirect_uri in strict mode."""
        # Mock feature flag and redirect URI
        mock_config_instance = mock_app_config.return_value
        mock_config_instance.get.side_effect = lambda key: {
            "TA_MCP_OAUTH_STRICT_HTTPS_VALIDATION": "true",
            "TA_OAUTH_REDIRECT_URI": "http://localhost:8000/oauth/callback",  # Localhost OK
        }.get(key, "default")

        # Should not raise
        config = McpServerConfig(
            name="test-server",
            transport="http",
            url="https://mcp.example.com",
            auth_server="https://auth.example.com",
            scopes=["read", "write"],
        )
        assert config.auth_server == "https://auth.example.com"


class TestHttpsEnforcementEdgeCases:
    """Test edge cases for HTTPS enforcement."""

    def test_validate_https_url_with_port(self):
        """HTTPS URLs with non-standard ports should be valid."""
        assert validate_https_url("https://example.com:8443") is True
        assert validate_https_url("https://example.com:9443/path") is True

    def test_validate_https_url_with_path(self):
        """HTTPS URLs with paths should be valid."""
        assert validate_https_url("https://example.com/oauth/authorize") is True
        assert validate_https_url("https://example.com/path/to/endpoint") is True

    def test_validate_https_url_with_query(self):
        """HTTPS URLs with query parameters should be valid."""
        assert validate_https_url("https://example.com/auth?client_id=123") is True

    def test_validate_https_url_localhost_with_subdomain(self):
        """localhost subdomains should not be treated as localhost."""
        # "notlocalhost.com" is NOT localhost
        assert validate_https_url("http://notlocalhost.com", allow_localhost=True) is False

        # "sub.localhost" might be localhost (depends on implementation)
        # For strict security, treat only exact "localhost" as localhost
        assert validate_https_url("http://sub.localhost", allow_localhost=True) is False
