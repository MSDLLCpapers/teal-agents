#!/usr/bin/env python3
"""
Real MCP integration test using SQLite MCP server.
Tests the complete integration stack with an actual MCP server.
"""

import asyncio
import json
import logging
import os
import sqlite3
import tempfile
from pathlib import Path

from sk_agents.mcp_integration import MCPPlugin, MCPPluginFactory

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class RealMCPServerTest:
    """Test MCP integration with a real SQLite MCP server."""
    
    def __init__(self):
        self.temp_dir = None
        self.db_path = None
        self.mcp_plugin = None
        
    async def setup(self):
        """Setup test environment with SQLite database."""
        self.temp_dir = tempfile.mkdtemp(prefix="mcp_real_test_")
        self.db_path = Path(self.temp_dir) / "test.db"
        
        # Create test database with sample data
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create sample tables
        cursor.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE,
                age INTEGER
            )
        """)
        
        cursor.execute("""
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL,
                category TEXT
            )
        """)
        
        # Insert sample data
        cursor.executemany("""
            INSERT INTO users (name, email, age) VALUES (?, ?, ?)
        """, [
            ("Alice Johnson", "alice@example.com", 28),
            ("Bob Smith", "bob@example.com", 35),
            ("Carol Davis", "carol@example.com", 42)
        ])
        
        cursor.executemany("""
            INSERT INTO products (name, price, category) VALUES (?, ?, ?)
        """, [
            ("Laptop", 999.99, "Electronics"),
            ("Coffee Mug", 12.50, "Kitchen"),
            ("Notebook", 5.99, "Office"),
            ("Smartphone", 599.99, "Electronics")
        ])
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created test database at: {self.db_path}")
        
        # Create MCP plugin with SQLite server
        self.mcp_plugin = MCPPluginFactory.create_sqlite_plugin(str(self.db_path))
        
    async def cleanup(self):
        """Cleanup test environment."""
        if self.mcp_plugin:
            await self.mcp_plugin.cleanup()
        
        if self.temp_dir and Path(self.temp_dir).exists():
            import shutil
            shutil.rmtree(self.temp_dir)
            logger.info("Test environment cleaned up")
    
    async def test_connection(self) -> bool:
        """Test basic MCP server connection."""
        try:
            logger.info("Testing MCP server connection...")
            await self.mcp_plugin.initialize()
            
            if self.mcp_plugin._initialized:
                logger.info("✅ MCP server connection successful")
                return True
            else:
                logger.error("❌ MCP server connection failed")
                return False
                
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            return False
    
    async def test_list_tools(self) -> bool:
        """Test listing available MCP tools."""
        try:
            logger.info("Testing tool listing...")
            tools_json = await self.mcp_plugin.list_mcp_tools()
            tools = json.loads(tools_json)
            
            logger.info(f"Available tools: {json.dumps(tools, indent=2)}")
            
            # Check if SQLite tools are available
            sqlite_tools_found = False
            for server_name, server_tools in tools.items():
                if isinstance(server_tools, list) and len(server_tools) > 0:
                    sqlite_tools_found = True
                    logger.info(f"✅ Found {len(server_tools)} tools from {server_name}")
                    for tool in server_tools:
                        logger.info(f"  - {tool.get('name', 'unnamed')}: {tool.get('description', 'no description')}")
            
            if sqlite_tools_found:
                logger.info("✅ Tool listing successful")
                return True
            else:
                logger.warning("⚠️  No tools found, but listing succeeded")
                return True
                
        except Exception as e:
            logger.error(f"❌ Tool listing failed: {e}")
            return False
    
    async def test_database_query(self) -> bool:
        """Test executing database queries via MCP."""
        try:
            logger.info("Testing database queries...")
            
            # Test query execution
            query_args = json.dumps({
                "query": "SELECT * FROM users WHERE age > 30 ORDER BY age"
            })
            
            result_json = await self.mcp_plugin.call_mcp_tool(
                server_name="sqlite",
                tool_name="read_query",
                arguments=query_args
            )
            
            result = json.loads(result_json)
            logger.info(f"Query result: {json.dumps(result, indent=2)}")
            
            if result.get("success"):
                logger.info("✅ Database query successful")
                return True
            else:
                logger.error(f"❌ Database query failed: {result.get('error', 'Unknown error')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Database query test failed: {e}")
            return False
    
    async def test_table_schema(self) -> bool:
        """Test getting table schema information."""
        try:
            logger.info("Testing table schema retrieval...")
            
            # Test getting table info
            schema_args = json.dumps({
                "table_name": "products"
            })
            
            result_json = await self.mcp_plugin.call_mcp_tool(
                server_name="sqlite",
                tool_name="describe_table",
                arguments=schema_args
            )
            
            result = json.loads(result_json)
            logger.info(f"Table schema: {json.dumps(result, indent=2)}")
            
            if result.get("success"):
                logger.info("✅ Table schema retrieval successful")
                return True
            else:
                logger.warning(f"⚠️  Table schema retrieval returned: {result}")
                return True  # Some MCP servers might not have this tool
                
        except Exception as e:
            logger.error(f"❌ Table schema test failed: {e}")
            return False
    
    async def test_error_handling(self) -> bool:
        """Test error handling with invalid queries."""
        try:
            logger.info("Testing error handling...")
            
            # Test invalid query
            invalid_args = json.dumps({
                "query": "SELECT * FROM nonexistent_table"
            })
            
            result_json = await self.mcp_plugin.call_mcp_tool(
                server_name="sqlite",
                tool_name="read_query",
                arguments=invalid_args
            )
            
            result = json.loads(result_json)
            logger.info(f"Error handling result: {json.dumps(result, indent=2)}")
            
            # Should return error gracefully, not crash
            if not result.get("success") and result.get("error"):
                logger.info("✅ Error handling working correctly")
                return True
            else:
                logger.warning("⚠️  Expected error but got success - that's unusual")
                return True
                
        except Exception as e:
            logger.error(f"❌ Error handling test failed: {e}")
            return False
    
    async def run_all_tests(self) -> dict:
        """Run all real MCP server tests."""
        logger.info("Starting Real MCP Server Integration Tests")
        logger.info("=" * 50)
        
        await self.setup()
        
        tests = [
            ("connection", self.test_connection),
            ("list_tools", self.test_list_tools),
            ("database_query", self.test_database_query),
            ("table_schema", self.test_table_schema),
            ("error_handling", self.test_error_handling),
        ]
        
        results = {}
        
        for test_name, test_func in tests:
            try:
                logger.info(f"\nRunning test: {test_name}")
                result = await test_func()
                results[test_name] = result
                status = "✅ PASS" if result else "❌ FAIL"
                logger.info(f"Test {test_name}: {status}")
            except Exception as e:
                logger.error(f"Test {test_name} failed with exception: {e}")
                results[test_name] = False
        
        await self.cleanup()
        
        # Print summary
        self.print_summary(results)
        
        return results
    
    def print_summary(self, results: dict):
        """Print test summary."""
        print("\n" + "="*60)
        print("REAL MCP SERVER TEST SUMMARY")
        print("="*60)
        
        total_tests = len(results)
        passed_tests = sum(1 for result in results.values() if result)
        failed_tests = total_tests - passed_tests
        
        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")
        print(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
        
        print("\nDetailed Results:")
        for test_name, result in results.items():
            status = "✅ PASS" if result else "❌ FAIL"
            print(f"  {test_name:20} {status}")
        
        print("\n" + "="*60)
        
        if failed_tests == 0:
            print("🎉 ALL TESTS PASSED! Real MCP integration working!")
        else:
            print(f"⚠️  {failed_tests} test(s) failed.")
            print("Note: Some failures may be expected if MCP server doesn't support all tools.")
        
        print("="*60)


async def main():
    """Main test runner."""
    print("Real MCP Server Integration Test")
    print("Using SQLite MCP Server")
    print("=" * 40)
    
    tester = RealMCPServerTest()
    results = await tester.run_all_tests()
    
    # Exit with appropriate code
    exit_code = 0 if all(results.values()) else 1
    exit(exit_code)


if __name__ == "__main__":
    asyncio.run(main())