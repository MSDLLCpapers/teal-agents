"""
Tests for OAuth Scope Validation

Verifies scope validation prevents escalation attacks per OAuth 2.1 Section 3.3.
"""

import pytest

from sk_agents.auth.oauth_client import OAuthClient
from sk_agents.auth.oauth_models import TokenResponse


class TestScopeValidation:
    """Test scope validation to prevent escalation attacks."""

    def test_validate_scopes_exact_match(self):
        """Validation passes when returned scopes match requested scopes."""
        requested = ["read", "write"]
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="read write",  # Exact match
        )

        # Should not raise
        OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_subset(self):
        """Validation passes when returned scopes are subset of requested."""
        requested = ["read", "write", "delete"]
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="read write",  # Subset (missing delete)
        )

        # Should not raise (server granted fewer scopes)
        OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_escalation_attack(self):
        """Validation fails when returned scopes exceed requested (escalation attack)."""
        requested = ["read"]
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="read write delete admin",  # ESCALATION!
        )

        with pytest.raises(ValueError, match="unauthorized scopes"):
            OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_with_no_requested(self):
        """Validation passes when no scopes were requested (any granted scopes OK)."""
        requested = None
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="read write",
        )

        # Should not raise
        OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_with_empty_requested(self):
        """Validation passes when empty scopes were requested."""
        requested = []
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="read write",
        )

        # Should not raise
        OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_with_no_returned(self):
        """Validation passes when server omits scope (OAuth 2.1: defaults to all requested)."""
        requested = ["read", "write"]
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope=None,  # Server omitted scope field
        )

        # Should not raise (OAuth 2.1: assumes all requested scopes granted)
        OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_case_sensitive(self):
        """Scope validation is case-sensitive."""
        requested = ["read"]
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="READ",  # Different case - treated as different scope
        )

        # Should raise - "READ" is not in requested ["read"]
        with pytest.raises(ValueError, match="unauthorized scopes"):
            OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_order_independent(self):
        """Scope validation is order-independent."""
        requested = ["read", "write", "delete"]
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="delete write read",  # Different order, same scopes
        )

        # Should not raise
        OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_with_extra_whitespace(self):
        """Scope validation handles extra whitespace in scope string."""
        requested = ["read", "write"]
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="  read   write  ",  # Extra whitespace
        )

        # Should not raise (whitespace is stripped during split)
        OAuthClient.validate_token_scopes(requested, token_response)

    def test_validate_scopes_partial_escalation(self):
        """Validation catches partial escalation (some scopes legitimate, some not)."""
        requested = ["read", "write"]
        token_response = TokenResponse(
            access_token="token",
            token_type="Bearer",
            expires_in=3600,
            scope="read write admin",  # read/write OK, admin NOT requested
        )

        with pytest.raises(ValueError, match="admin"):
            OAuthClient.validate_token_scopes(requested, token_response)


class TestScopeValidationInTokenExchange:
    """Test scope validation is called during token exchange."""

    @pytest.mark.asyncio
    async def test_token_exchange_validates_scopes(self):
        """Token exchange calls scope validation."""
        from unittest.mock import AsyncMock, Mock, patch

        from sk_agents.auth.oauth_models import TokenRequest

        # Mock the HTTP client
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "read write",
        }

        mock_client = Mock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            # Mock validate_token_scopes to verify it's called
            with patch.object(OAuthClient, "validate_token_scopes") as mock_validate:
                # Execute token exchange
                client = OAuthClient()
                token_request = TokenRequest(
                    token_endpoint="https://auth.example.com/token",
                    grant_type="authorization_code",
                    code="auth-code",
                    redirect_uri="https://app.example.com/callback",
                    code_verifier="verifier",
                    resource="https://mcp.example.com",
                    client_id="test-client",
                    requested_scopes=["read", "write"],  # For validation
                )

                await client.exchange_code_for_tokens(token_request)

                # Verify validation was called
                assert mock_validate.called
                call_args = mock_validate.call_args
                assert call_args[0][0] == ["read", "write"]  # requested_scopes
                assert call_args[0][1].access_token == "test-token"  # token_response
