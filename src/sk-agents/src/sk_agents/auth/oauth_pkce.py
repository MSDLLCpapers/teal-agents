"""
PKCE (Proof Key for Code Exchange) Implementation

Implements PKCE as required by OAuth 2.1 and MCP specification.
PKCE prevents authorization code interception attacks.

References:
- OAuth 2.1 Section 7.5.2
- RFC 7636: Proof Key for Code Exchange
"""

import base64
import hashlib
import secrets


def generate_code_verifier() -> str:
    """
    Generate cryptographically random code verifier.

    Per OAuth 2.1 spec, code verifier must be:
    - 43-128 characters long
    - Use characters [A-Z] / [a-z] / [0-9] / "-" / "." / "_" / "~"

    Returns:
        str: Base64url-encoded random verifier (43-128 chars)
    """
    # Generate 32 random bytes (provides 43 base64url characters)
    random_bytes = secrets.token_bytes(32)
    # Base64url encode (URL-safe, no padding)
    verifier = base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    return verifier


def generate_code_challenge(verifier: str) -> str:
    """
    Generate PKCE code challenge from verifier using S256 method.

    Per OAuth 2.1 spec:
    - challenge = BASE64URL(SHA256(verifier))

    Args:
        verifier: Code verifier from generate_code_verifier()

    Returns:
        str: Base64url-encoded SHA256 hash of verifier
    """
    # SHA256 hash
    sha256_hash = hashlib.sha256(verifier.encode('utf-8')).digest()
    # Base64url encode (URL-safe, no padding)
    challenge = base64.urlsafe_b64encode(sha256_hash).decode('utf-8').rstrip('=')
    return challenge


def validate_code_verifier(verifier: str) -> bool:
    """
    Validate code verifier meets OAuth 2.1 requirements.

    Args:
        verifier: Code verifier to validate

    Returns:
        bool: True if valid, False otherwise
    """
    # Check length (43-128 characters)
    if not (43 <= len(verifier) <= 128):
        return False

    # Check allowed characters
    allowed_chars = set(
        'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~'
    )
    if not all(c in allowed_chars for c in verifier):
        return False

    return True


class PKCEManager:
    """
    Manager for PKCE generation and validation.

    Provides high-level interface for PKCE operations in OAuth flows.
    """

    @staticmethod
    def generate_pkce_pair() -> tuple[str, str]:
        """
        Generate PKCE verifier and challenge pair.

        Returns:
            tuple: (verifier, challenge)
        """
        verifier = generate_code_verifier()
        challenge = generate_code_challenge(verifier)
        return verifier, challenge

    @staticmethod
    def validate_verifier(verifier: str) -> bool:
        """
        Validate code verifier meets requirements.

        Args:
            verifier: Code verifier to validate

        Returns:
            bool: True if valid
        """
        return validate_code_verifier(verifier)

    @staticmethod
    def verify_challenge(verifier: str, challenge: str) -> bool:
        """
        Verify that challenge matches verifier.

        Used by authorization server (not typically by client).

        Args:
            verifier: Code verifier
            challenge: Code challenge to verify

        Returns:
            bool: True if challenge matches verifier
        """
        expected_challenge = generate_code_challenge(verifier)
        return expected_challenge == challenge
