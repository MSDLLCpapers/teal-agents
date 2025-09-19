#!/usr/bin/env python3
"""
Test script for session-scoped MCP connection management.

This script demonstrates:
1. Creating session-scoped MCP clients
2. Verifying session isolation
3. Testing automatic cleanup
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src" / "sk-agents" / "src"
sys.path.insert(0, str(src_path))

from sk_agents.mcp_client import SessionMcpClientRegistry, get_mcp_client_for_session, cleanup_mcp_session

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_session_isolation():
    """Test that different sessions get isolated MCP clients."""
    logger.info("Testing session isolation...")

    # Get clients for different sessions
    client1 = await get_mcp_client_for_session("session_1")
    client2 = await get_mcp_client_for_session("session_2")
    client1_again = await get_mcp_client_for_session("session_1")

    # Verify isolation
    assert client1 != client2, "Different sessions should have different clients"
    assert client1 is client1_again, "Same session should reuse client"

    logger.info("✓ Session isolation working correctly")


async def test_session_cleanup():
    """Test that session cleanup removes client from registry."""
    logger.info("Testing session cleanup...")

    session_id = "test_cleanup_session"

    # Create client
    client = await get_mcp_client_for_session(session_id)
    active_sessions = SessionMcpClientRegistry.get_active_sessions()
    assert session_id in active_sessions, f"Session {session_id} should be active"

    # Cleanup session
    await cleanup_mcp_session(session_id)
    active_sessions_after = SessionMcpClientRegistry.get_active_sessions()
    assert session_id not in active_sessions_after, f"Session {session_id} should be cleaned up"

    logger.info("✓ Session cleanup working correctly")


async def test_auto_cleanup_scheduling():
    """Test that auto-cleanup is scheduled for new sessions."""
    logger.info("Testing auto-cleanup scheduling...")

    session_id = "test_auto_cleanup"

    # Create client (should schedule cleanup)
    client = await get_mcp_client_for_session(session_id)

    # Check that cleanup task is scheduled
    cleanup_tasks = SessionMcpClientRegistry._cleanup_tasks
    assert session_id in cleanup_tasks, f"Cleanup task should be scheduled for {session_id}"

    # Manual cleanup
    await cleanup_mcp_session(session_id)

    logger.info("✓ Auto-cleanup scheduling working correctly")


async def main():
    """Run all session-scoped MCP tests."""
    logger.info("Starting session-scoped MCP connection tests...")

    try:
        await test_session_isolation()
        await test_session_cleanup()
        await test_auto_cleanup_scheduling()

        logger.info("🎉 All tests passed! Session-scoped MCP implementation is working correctly.")

    except Exception as e:
        logger.error(f"❌ Test failed: {e}")
        raise

    finally:
        # Clean up any remaining sessions
        active_sessions = SessionMcpClientRegistry.get_active_sessions()
        for session_id in active_sessions:
            try:
                await cleanup_mcp_session(session_id)
            except Exception as e:
                logger.warning(f"Failed to cleanup session {session_id}: {e}")


if __name__ == "__main__":
    asyncio.run(main())