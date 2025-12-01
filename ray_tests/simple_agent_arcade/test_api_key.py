#!/usr/bin/env python3
"""
Quick test script to verify OpenAI API key is working.

Usage:
    python test_api_key.py YOUR_API_KEY_HERE
"""

import sys
from openai import OpenAI


def test_api_key(api_key: str):
    """Test if the OpenAI API key works by making a simple request."""

    print("=" * 60)
    print("Testing OpenAI API Key")
    print("=" * 60)

    try:
        # Initialize client
        print("\n[1/3] Initializing OpenAI client...")
        client = OpenAI(api_key=api_key)
        print("✓ Client initialized")

        # Make a simple completion request
        print("\n[2/3] Making test API call (gpt-4o-mini)...")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "user", "content": "Say 'API key is working!' and nothing else."}
            ],
            max_tokens=10
        )
        print("✓ API call successful")

        # Display response
        print("\n[3/3] Response from API:")
        print("-" * 60)
        print(response.choices[0].message.content)
        print("-" * 60)

        # Summary
        print("\n" + "=" * 60)
        print("✓ SUCCESS! Your OpenAI API key is working correctly.")
        print("=" * 60)
        print(f"\nModel used: {response.model}")
        print(f"Tokens used: {response.usage.total_tokens}")
        print(f"  - Prompt tokens: {response.usage.prompt_tokens}")
        print(f"  - Completion tokens: {response.usage.completion_tokens}")

        return True

    except Exception as e:
        print("\n" + "=" * 60)
        print("✗ ERROR! API key test failed.")
        print("=" * 60)
        print(f"\nError type: {type(e).__name__}")
        print(f"Error message: {str(e)}")

        # Common error tips
        print("\nCommon issues:")
        print("  1. Invalid API key format")
        print("  2. API key has been revoked or expired")
        print("  3. Insufficient credits/quota")
        print("  4. Network connectivity issues")

        return False


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_api_key.py YOUR_API_KEY_HERE")
        print("\nExample:")
        print("  python test_api_key.py sk-proj-abcd1234...")
        sys.exit(1)

    api_key = sys.argv[1]

    # Basic validation
    if not api_key.startswith("sk-"):
        print("⚠ Warning: OpenAI API keys typically start with 'sk-'")
        print("  Your key: " + api_key[:10] + "...")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)

    success = test_api_key(api_key)
    sys.exit(0 if success else 1)
