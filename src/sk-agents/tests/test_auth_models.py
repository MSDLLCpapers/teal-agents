import pytest
from datetime import datetime, timedelta
from src.sk_agents.auth_storage.models import OAuth2AuthData


def test_oauth2_auth_data_valid_model():
    """Verify that a valid OAuth2AuthData model is created successfully."""
    valid_data = {
        "access_token": "some-token",
        "refresh_token": "some-refresh-token",
        "expires_at": datetime.now() + timedelta(hours=1),
        "scopes": ["scope1", "scope2"],
    }
    auth_data = OAuth2AuthData(**valid_data)
    assert auth_data.access_token == "some-token"
    assert "oauth2" == auth_data.auth_type
    assert isinstance(auth_data.expires_at, datetime)

def test_oauth2_auth_data_missing_access_token():
    """Verify that the model raises a validation error for a missing access token."""
    invalid_data = {
        "refresh_token": "some-refresh-token",
        "expires_at": datetime.now(),
        "scopes": ["scope1"],
    }
    with pytest.raises(ValueError, match="access_token"):
        OAuth2AuthData(**invalid_data)

def test_oauth2_auth_data_invalid_expires_at_type():
    """Verify that the model raises a validation error for an invalid expires_at type."""
    invalid_data = {
        "access_token": "some-token",
        "expires_at": "not-a-datetime",
        "scopes": ["scope1"],
    }
    with pytest.raises(ValueError, match="expires_at"):
        OAuth2AuthData(**invalid_data)