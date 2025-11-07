"""
Tests for WWW-Authenticate Header Parsing

Verifies parsing of WWW-Authenticate challenges per RFC 6750 and RFC 9728.
"""

import pytest
from sk_agents.auth.oauth_error_handler import (
    parse_www_authenticate_header,
    extract_field_from_www_authenticate,
    WWWAuthenticateChallenge,
    OAuthErrorHandler,
)


class TestWWWAuthenticateParsing:
    """Test parsing of WWW-Authenticate headers."""

    def test_parse_simple_bearer_challenge(self):
        """Parse basic Bearer challenge."""
        header = 'Bearer realm="example"'
        challenge = parse_www_authenticate_header(header)

        assert challenge is not None
        assert challenge.realm == "example"
        assert challenge.error is None

    def test_parse_challenge_with_error(self):
        """Parse challenge with error code."""
        header = 'Bearer realm="example", error="invalid_token"'
        challenge = parse_www_authenticate_header(header)

        assert challenge is not None
        assert challenge.realm == "example"
        assert challenge.error == "invalid_token"

    def test_parse_challenge_with_all_fields(self):
        """Parse challenge with all RFC 6750 fields."""
        header = (
            'Bearer realm="example", '
            'error="insufficient_scope", '
            'error_description="The access token requires additional scopes", '
            'error_uri="https://docs.example.com/errors", '
            'scope="read write"'
        )
        challenge = parse_www_authenticate_header(header)

        assert challenge is not None
        assert challenge.realm == "example"
        assert challenge.error == "insufficient_scope"
        assert challenge.error_description == "The access token requires additional scopes"
        assert challenge.error_uri == "https://docs.example.com/errors"
        assert challenge.scope == "read write"

    def test_parse_challenge_with_resource_metadata(self):
        """Parse challenge with RFC 9728 resource_metadata field."""
        header = (
            'Bearer error="invalid_token", '
            'resource_metadata="https://api.example.com/.well-known/oauth-protected-resource"'
        )
        challenge = parse_www_authenticate_header(header)

        assert challenge is not None
        assert challenge.error == "invalid_token"
        assert (
            challenge.resource_metadata
            == "https://api.example.com/.well-known/oauth-protected-resource"
        )

    def test_parse_challenge_unquoted_values(self):
        """Parse challenge with unquoted parameter values."""
        header = 'Bearer realm=example, error=invalid_token'
        challenge = parse_www_authenticate_header(header)

        assert challenge is not None
        assert challenge.realm == "example"
        assert challenge.error == "invalid_token"

    def test_parse_challenge_mixed_quoted_unquoted(self):
        """Parse challenge with mix of quoted and unquoted values."""
        header = 'Bearer realm="example", error=invalid_token, scope="read write"'
        challenge = parse_www_authenticate_header(header)

        assert challenge is not None
        assert challenge.realm == "example"
        assert challenge.error == "invalid_token"
        assert challenge.scope == "read write"

    def test_parse_non_bearer_challenge(self):
        """Non-Bearer challenges return None."""
        header = 'Basic realm="example"'
        challenge = parse_www_authenticate_header(header)

        assert challenge is None

    def test_parse_empty_header(self):
        """Empty header returns None."""
        challenge = parse_www_authenticate_header("")
        assert challenge is None

    def test_parse_none_header(self):
        """None header returns None."""
        challenge = parse_www_authenticate_header(None)
        assert challenge is None

    def test_parse_challenge_case_insensitive_bearer(self):
        """Bearer keyword is case-insensitive."""
        header = 'bearer realm="example"'  # lowercase
        challenge = parse_www_authenticate_header(header)

        assert challenge is not None
        assert challenge.realm == "example"


class TestWWWAuthenticateChallengeHelpers:
    """Test WWWAuthenticateChallenge helper methods."""

    def test_scopes_property(self):
        """Scopes property returns list of scopes."""
        challenge = WWWAuthenticateChallenge(scope="read write delete")
        assert challenge.scopes == ["read", "write", "delete"]

    def test_scopes_property_empty(self):
        """Scopes property returns empty list when no scope."""
        challenge = WWWAuthenticateChallenge(scope=None)
        assert challenge.scopes == []

    def test_requires_reauth_for_invalid_token(self):
        """requires_reauth returns True for invalid_token."""
        challenge = WWWAuthenticateChallenge(error="invalid_token")
        assert challenge.requires_reauth() is True

    def test_requires_reauth_for_insufficient_scope(self):
        """requires_reauth returns True for insufficient_scope."""
        challenge = WWWAuthenticateChallenge(error="insufficient_scope")
        assert challenge.requires_reauth() is True

    def test_requires_reauth_for_other_errors(self):
        """requires_reauth returns False for other errors."""
        challenge = WWWAuthenticateChallenge(error="server_error")
        assert challenge.requires_reauth() is False

    def test_is_token_expired(self):
        """is_token_expired returns True for invalid_token."""
        challenge = WWWAuthenticateChallenge(error="invalid_token")
        assert challenge.is_token_expired() is True

    def test_is_insufficient_scope(self):
        """is_insufficient_scope returns True for insufficient_scope."""
        challenge = WWWAuthenticateChallenge(error="insufficient_scope")
        assert challenge.is_insufficient_scope() is True


class TestExtractField:
    """Test extract_field_from_www_authenticate convenience function."""

    def test_extract_error_field(self):
        """Extract error field."""
        header = 'Bearer error="invalid_token"'
        error = extract_field_from_www_authenticate(header, "error")
        assert error == "invalid_token"

    def test_extract_scope_field(self):
        """Extract scope field."""
        header = 'Bearer scope="read write"'
        scope = extract_field_from_www_authenticate(header, "scope")
        assert scope == "read write"

    def test_extract_resource_metadata_field(self):
        """Extract resource_metadata field."""
        header = 'Bearer resource_metadata="https://example.com/.well-known/oauth-protected-resource"'
        metadata = extract_field_from_www_authenticate(header, "resource_metadata")
        assert metadata == "https://example.com/.well-known/oauth-protected-resource"

    def test_extract_missing_field(self):
        """Extracting missing field returns None."""
        header = 'Bearer realm="example"'
        error = extract_field_from_www_authenticate(header, "error")
        assert error is None


class TestOAuthErrorHandler:
    """Test OAuthErrorHandler utility methods."""

    def test_handle_401_response_with_www_authenticate(self):
        """handle_401_response extracts WWW-Authenticate challenge."""
        headers = {"WWW-Authenticate": 'Bearer error="invalid_token"'}
        challenge = OAuthErrorHandler.handle_401_response(headers)

        assert challenge is not None
        assert challenge.error == "invalid_token"

    def test_handle_401_response_case_insensitive_header(self):
        """handle_401_response handles lowercase header name."""
        headers = {"www-authenticate": 'Bearer error="invalid_token"'}
        challenge = OAuthErrorHandler.handle_401_response(headers)

        assert challenge is not None
        assert challenge.error == "invalid_token"

    def test_handle_401_response_missing_header(self):
        """handle_401_response returns None when header missing."""
        headers = {}
        challenge = OAuthErrorHandler.handle_401_response(headers)
        assert challenge is None

    def test_should_refresh_token_for_invalid_token(self):
        """should_refresh_token returns True for invalid_token."""
        challenge = WWWAuthenticateChallenge(error="invalid_token")
        assert OAuthErrorHandler.should_refresh_token(challenge) is True

    def test_should_refresh_token_for_other_errors(self):
        """should_refresh_token returns False for other errors."""
        challenge = WWWAuthenticateChallenge(error="insufficient_scope")
        assert OAuthErrorHandler.should_refresh_token(challenge) is False

    def test_should_reauthorize_for_insufficient_scope(self):
        """should_reauthorize returns True for insufficient_scope."""
        challenge = WWWAuthenticateChallenge(error="insufficient_scope")
        assert OAuthErrorHandler.should_reauthorize(challenge) is True

    def test_should_reauthorize_for_invalid_token(self):
        """should_reauthorize returns False for invalid_token (refresh instead)."""
        challenge = WWWAuthenticateChallenge(error="invalid_token")
        assert OAuthErrorHandler.should_reauthorize(challenge) is False

    def test_get_required_scopes(self):
        """get_required_scopes extracts scopes from challenge."""
        challenge = WWWAuthenticateChallenge(
            error="insufficient_scope", scope="read write admin"
        )
        scopes = OAuthErrorHandler.get_required_scopes(challenge)
        assert scopes == ["read", "write", "admin"]

    def test_get_required_scopes_no_challenge(self):
        """get_required_scopes returns empty list when no challenge."""
        scopes = OAuthErrorHandler.get_required_scopes(None)
        assert scopes == []
