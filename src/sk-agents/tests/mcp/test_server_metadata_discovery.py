"""
Tests for Server Metadata Discovery

Verifies RFC 8414 (Authorization Server Metadata) and RFC 9728 (Protected Resource Metadata)
discovery implementation.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from sk_agents.auth.server_metadata import ServerMetadataCache, AuthServerMetadata, ProtectedResourceMetadata
from sk_agents.auth.oauth_client import OAuthClient


class TestAuthServerMetadataDiscovery:
    """Test RFC 8414 authorization server metadata discovery."""

    @pytest.mark.asyncio
    async def test_fetch_auth_server_metadata_success(self):
        """Test successful RFC 8414 discovery."""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issuer": "https://auth.example.com",
            "authorization_endpoint": "https://auth.example.com/oauth/authorize",
            "token_endpoint": "https://auth.example.com/oauth/token",
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
        }

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            cache = ServerMetadataCache()
            metadata = await cache.fetch_auth_server_metadata("https://auth.example.com")

            assert str(metadata.issuer) == "https://auth.example.com/"
            assert str(metadata.authorization_endpoint) == "https://auth.example.com/oauth/authorize"
            assert str(metadata.token_endpoint) == "https://auth.example.com/oauth/token"
            assert "S256" in metadata.code_challenge_methods_supported

    @pytest.mark.asyncio
    async def test_fetch_auth_server_metadata_404(self):
        """Test handling of 404 response (server doesn't support discovery)."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            cache = ServerMetadataCache()
            with pytest.raises(Exception):
                await cache.fetch_auth_server_metadata("https://auth.example.com")

    @pytest.mark.asyncio
    async def test_metadata_cache_hit(self):
        """Test cache hit returns cached metadata without HTTP request."""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issuer": "https://auth.example.com",
            "authorization_endpoint": "https://auth.example.com/oauth/authorize",
            "token_endpoint": "https://auth.example.com/oauth/token",
            "response_types_supported": ["code"],
        }

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            cache = ServerMetadataCache(ttl=10)

            # First call - fetches
            metadata1 = await cache.fetch_auth_server_metadata("https://auth.example.com")

            # Second call - from cache
            metadata2 = await cache.fetch_auth_server_metadata("https://auth.example.com")

            assert metadata1.issuer == metadata2.issuer
            # Only one HTTP call should have been made
            assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_auth_server_metadata_without_pkce(self):
        """Test warning when server doesn't advertise PKCE support."""
        # Mock HTTP response without PKCE support
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "issuer": "https://auth.example.com",
            "authorization_endpoint": "https://auth.example.com/oauth/authorize",
            "token_endpoint": "https://auth.example.com/oauth/token",
            "response_types_supported": ["code"],
            # No code_challenge_methods_supported
        }

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            cache = ServerMetadataCache()
            # Should not raise, but should log warning
            metadata = await cache.fetch_auth_server_metadata("https://auth.example.com")
            assert str(metadata.issuer) == "https://auth.example.com/"
            assert metadata.code_challenge_methods_supported is None


class TestProtectedResourceMetadataDiscovery:
    """Test RFC 9728 protected resource metadata discovery."""

    @pytest.mark.asyncio
    async def test_fetch_prm_success(self):
        """Test successful RFC 9728 discovery."""
        # Mock HTTP response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "resource": "https://mcp.example.com",
            "authorization_servers": ["https://auth.example.com"],
            "scopes_supported": ["read", "write"],
        }

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            cache = ServerMetadataCache()
            prm = await cache.fetch_protected_resource_metadata("https://mcp.example.com")

            assert prm is not None
            assert str(prm.resource) == "https://mcp.example.com/"
            assert "https://auth.example.com" in prm.authorization_servers
            assert prm.scopes_supported == ["read", "write"]

    @pytest.mark.asyncio
    async def test_fetch_prm_404_returns_none(self):
        """Test that 404 response returns None (PRM is optional)."""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            cache = ServerMetadataCache()
            prm = await cache.fetch_protected_resource_metadata("https://mcp.example.com")

            # Should return None, not raise
            assert prm is None

    @pytest.mark.asyncio
    async def test_prm_cache_none_result(self):
        """Test that None result (404) is cached."""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            cache = ServerMetadataCache(ttl=10)

            # First call - fetches (404)
            prm1 = await cache.fetch_protected_resource_metadata("https://mcp.example.com")

            # Second call - from cache
            prm2 = await cache.fetch_protected_resource_metadata("https://mcp.example.com")

            assert prm1 is None
            assert prm2 is None
            # Only one HTTP call should have been made
            assert mock_client.get.call_count == 1


class TestOAuthClientWithDiscovery:
    """Test OAuth client integration with metadata discovery."""

    @pytest.mark.asyncio
    async def test_initiate_flow_uses_discovered_authorization_endpoint(self):
        """Test that initiate_authorization_flow uses discovered authorization_endpoint."""
        from sk_agents.tealagents.v1alpha1.config import McpServerConfig

        # Create test config
        with patch("ska_utils.AppConfig") as mock_app_config:
            mock_config_instance = mock_app_config.return_value
            mock_config_instance.get.side_effect = lambda key: {
                "TA_MCP_OAUTH_STRICT_HTTPS_VALIDATION": "false",
                "TA_OAUTH_REDIRECT_URI": "https://app.example.com/callback",
                "TA_OAUTH_CLIENT_NAME": "test-client",
            }.get(key, "default")

            server_config = McpServerConfig(
                name="test-server",
                transport="http",
                url="https://mcp.example.com",
                auth_server="https://auth.example.com",
                scopes=["read", "write"],
            )

        # Mock RFC 8414 response
        mock_auth_server_response = Mock()
        mock_auth_server_response.status_code = 200
        mock_auth_server_response.json.return_value = {
            "issuer": "https://auth.example.com",
            "authorization_endpoint": "https://auth.example.com/oauth/authorize",
            "token_endpoint": "https://auth.example.com/oauth/token",
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
        }

        # Mock RFC 9728 response (404 - optional)
        mock_prm_response = Mock()
        mock_prm_response.status_code = 404

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        # Return different responses based on URL
        async def mock_get(url):
            if "oauth-authorization-server" in url:
                return mock_auth_server_response
            else:
                return mock_prm_response

        mock_client.get = AsyncMock(side_effect=mock_get)

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("ska_utils.AppConfig") as mock_app_config_inner:
                mock_config_inner_instance = mock_app_config_inner.return_value
                mock_config_inner_instance.get.return_value = "test-client"
                
                client = OAuthClient()
                auth_url = await client.initiate_authorization_flow(server_config, "test_user")

            # Verify uses discovered authorization endpoint
            assert "auth.example.com/oauth/authorize" in auth_url
            assert "response_type=code" in auth_url
            assert "code_challenge=" in auth_url

    @pytest.mark.asyncio
    async def test_discovery_failure_falls_back_to_manual_config(self):
        """Test that discovery failure falls back to manual configuration."""
        from sk_agents.tealagents.v1alpha1.config import McpServerConfig

        # Create test config
        with patch("ska_utils.AppConfig") as mock_app_config:
            mock_config_instance = mock_app_config.return_value
            mock_config_instance.get.side_effect = lambda key: {
                "TA_MCP_OAUTH_STRICT_HTTPS_VALIDATION": "false",
                "TA_OAUTH_REDIRECT_URI": "https://app.example.com/callback",
                "TA_OAUTH_CLIENT_NAME": "test-client",
            }.get(key, "default")

            server_config = McpServerConfig(
                name="test-server",
                transport="http",
                url="https://mcp.example.com",
                auth_server="https://auth.example.com",
                scopes=["read", "write"],
            )

        # Mock discovery failure (timeout)
        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            with patch("ska_utils.AppConfig") as mock_app_config_inner:
                mock_config_inner_instance = mock_app_config_inner.return_value
                mock_config_inner_instance.get.return_value = "test-client"
                
                client = OAuthClient()
                # Should not raise, should use fallback
                auth_url = await client.initiate_authorization_flow(server_config, "test_user")

            # Verify uses fallback endpoint
            assert "auth.example.com" in auth_url
            assert "/authorize" in auth_url  # Fallback appends /authorize
