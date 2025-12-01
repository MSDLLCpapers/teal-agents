#!/usr/bin/env python3
"""
Integration test for the Merck API custom chat completion.

This script tests the custom MerckChatCompletion client and factory
to ensure they work correctly with the Teal Agents platform.

Usage:
    python test_merck_integration.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent.resolve()
project_root = script_dir.parent.parent

# Add sk-agents source to path
sys.path.insert(0, str(project_root / "src" / "sk-agents" / "src"))
# Add shared utilities to path
sys.path.insert(0, str(project_root / "shared" / "ska_utils" / "src"))
# Add test directory to path (for merck_chat_completion imports)
sys.path.insert(0, str(script_dir))

from dotenv import load_dotenv
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)

from merck_chat_completion import MerckChatCompletion
from merck_chat_completion_factory import MerckChatCompletionFactory
from ska_utils import AppConfig


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_step(step_num: int, total: int, description: str):
    """Print a formatted step."""
    print(f"\n[{step_num}/{total}] {description}")


def print_success(message: str):
    """Print a success message."""
    print(f"✓ {message}")


def print_error(message: str):
    """Print an error message."""
    print(f"✗ {message}")


async def test_merck_chat_completion():
    """Test the MerckChatCompletion client directly."""
    
    print_header("Test 1: Direct MerckChatCompletion Client")
    
    # Load environment variables from local .env
    env_path = script_dir / ".env"
    load_dotenv(env_path)
    
    api_key = os.getenv("MERCK_API_KEY")
    api_root = os.getenv("MERCK_API_ROOT", "https://iapi-test.merck.com/gpt/v2")
    model_name = "gpt-5-2025-08-07"
    
    if not api_key or api_key == "your-x-merck-apikey-here":
        print_error("MERCK_API_KEY not configured in .env file")
        print("Please update src/sk-agents/.env with your actual API key")
        return False
    
    try:
        print_step(1, 3, "Initializing MerckChatCompletion client...")
        client = MerckChatCompletion(
            service_id="test_service",
            api_key=api_key,
            api_root=api_root,
            model_name=model_name,
        )
        print_success("Client initialized")
        
        print_step(2, 3, "Creating test chat history...")
        chat_history = ChatHistory()
        chat_history.add_user_message("Say 'Hello from Merck API!' and nothing else.")
        print_success("Chat history created")
        
        print_step(3, 3, "Making API call...")
        settings = OpenAIChatPromptExecutionSettings(
            max_tokens=20,
            temperature=0.7,
        )
        
        async with client:
            messages = await client.get_chat_message_contents(chat_history, settings)
        
        print_success("API call successful!")
        
        # Display response
        print("\n" + "-" * 70)
        print("Response from Merck API:")
        print("-" * 70)
        for message in messages:
            print(message.content)
            print("-" * 70)
            
            # Show metadata if available
            if message.metadata:
                usage = message.metadata.get("usage", {})
                if usage:
                    print(f"\nToken Usage:")
                    print(f"  - Prompt tokens: {usage.get('prompt_tokens', 'N/A')}")
                    print(f"  - Completion tokens: {usage.get('completion_tokens', 'N/A')}")
                    print(f"  - Total tokens: {usage.get('total_tokens', 'N/A')}")
        
        print_success("\nTest 1 PASSED: Direct client works correctly!")
        return True
        
    except Exception as e:
        print_error(f"Test 1 FAILED: {type(e).__name__}: {str(e)}")
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()
        return False


async def test_merck_factory():
    """Test the MerckChatCompletionFactory."""
    
    print_header("Test 2: MerckChatCompletionFactory")
    
    # Load environment variables from local .env
    env_path = script_dir / ".env"
    load_dotenv(env_path)
    
    try:
        print_step(1, 5, "Registering factory configs with AppConfig...")
        # Get and register the factory's required configs
        factory_configs = MerckChatCompletionFactory.get_configs()
        if factory_configs:
            AppConfig.add_configs(factory_configs)
        print_success("Configs registered")
        
        print_step(2, 5, "Initializing AppConfig...")
        app_config = AppConfig()
        print_success("AppConfig initialized")
        
        print_step(3, 5, "Creating MerckChatCompletionFactory...")
        factory = MerckChatCompletionFactory(app_config)
        print_success("Factory created")
        
        print_step(4, 5, "Getting chat completion client from factory...")
        model_name = "gpt-5-2025-08-07"
        client = factory.get_chat_completion_for_model_name(
            model_name=model_name,
            service_id="test_service_factory"
        )
        print_success(f"Client created for model: {model_name}")
        
        print_step(5, 5, "Testing client from factory...")
        chat_history = ChatHistory()
        chat_history.add_user_message("Respond with just 'Factory test successful!'")
        
        settings = OpenAIChatPromptExecutionSettings(
            max_tokens=10,
            temperature=0.7,
        )
        
        async with client:
            messages = await client.get_chat_message_contents(chat_history, settings)
        
        print_success("Factory-created client works!")
        
        # Display response
        print("\n" + "-" * 70)
        print("Response:")
        print("-" * 70)
        for message in messages:
            print(message.content)
        print("-" * 70)
        
        print_success("\nTest 2 PASSED: Factory works correctly!")
        return True
        
    except Exception as e:
        print_error(f"Test 2 FAILED: {type(e).__name__}: {str(e)}")
        import traceback
        print("\nFull traceback:")
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    
    print_header("Merck API Integration Tests")
    print("\nThis script tests the custom Merck API integration with Teal Agents")
    
    # Check .env file exists in test directory
    env_path = script_dir / ".env"
    if not env_path.exists():
        print_error(f".env file not found at: {env_path}")
        print("\nPlease create the .env file by copying .env.example:")
        print(f"  cp {script_dir}/.env.example {env_path}")
        return False
    
    print_success(f"Found .env file at: {env_path}")
    
    # Run tests
    results = []
    
    test1_result = await test_merck_chat_completion()
    results.append(("Direct Client Test", test1_result))
    
    test2_result = await test_merck_factory()
    results.append(("Factory Test", test2_result))
    
    # Print summary
    print_header("Test Summary")
    
    all_passed = True
    for test_name, result in results:
        status = "PASSED ✓" if result else "FAILED ✗"
        print(f"  {test_name}: {status}")
        if not result:
            all_passed = False
    
    print("\n" + "=" * 70)
    if all_passed:
        print("  ✓ All tests PASSED! Integration is working correctly.")
    else:
        print("  ✗ Some tests FAILED. Please review errors above.")
    print("=" * 70)
    
    return all_passed


if __name__ == "__main__":
    try:
        success = asyncio.run(main())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTests interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nUnexpected error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
