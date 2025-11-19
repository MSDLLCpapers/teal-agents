from datetime import datetime, timedelta, timezone

from sk_agents.auth_routes import TokenRefreshRequest
from sk_agents.auth_storage.models import OAuth2AuthData


class TestTokenRefreshRequest:
    """Test TokenRefreshRequest model."""

    def test_token_refresh_request_creation(self):
        """Test creating TokenRefreshRequest with required fields."""
        request = TokenRefreshRequest(
            client_id="test_client_id",
            client_secret="test_secret",
            scopes=["https://graph.microsoft.com/.default"]
        )
        
        assert request.client_id == "test_client_id"
        assert request.client_secret == "test_secret"
        assert request.scopes == ["https://graph.microsoft.com/.default"]
        assert request.authority == "https://login.microsoftonline.com/common"

    def test_token_refresh_request_public_client(self):
        """Test creating TokenRefreshRequest for public client."""
        request = TokenRefreshRequest(
            client_id="test_client_id",
            authority="https://login.microsoftonline.com/tenant",
            scopes=["scope1", "scope2"]
        )
        
        assert request.client_id == "test_client_id"
        assert request.client_secret is None
        assert request.authority == "https://login.microsoftonline.com/tenant"
        assert request.scopes == ["scope1", "scope2"]


class TestOAuth2AuthDataRefreshSupport:
    """Test OAuth2AuthData with refresh token support."""

    def test_oauth2_auth_data_with_refresh_token(self):
        """Test that OAuth2AuthData correctly handles refresh tokens."""
        auth_data = OAuth2AuthData(
            access_token="test_access_token",
            refresh_token="test_refresh_token",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["https://graph.microsoft.com/.default"]
        )
        
        assert auth_data.refresh_token == "test_refresh_token"
        assert auth_data.access_token == "test_access_token"
        assert len(auth_data.scopes) > 0

    def test_oauth2_auth_data_without_refresh_token(self):
        """Test OAuth2AuthData when refresh_token is None."""
        auth_data = OAuth2AuthData(
            access_token="test_access_token",
            refresh_token=None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            scopes=["https://graph.microsoft.com/.default"]
        )
        
        assert auth_data.refresh_token is None
        assert auth_data.access_token == "test_access_token"