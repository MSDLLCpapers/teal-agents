#!/usr/bin/env python3
"""
Wrapper script to run SQLite MCP server.
This script allows the SQLite MCP server to be executed properly.
"""

import sys
import asyncio
from mcp_server_sqlite import server

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python run_sqlite_mcp_server.py <db_path>")
        sys.exit(1)
    
    db_path = sys.argv[1]
    asyncio.run(server.main(db_path))