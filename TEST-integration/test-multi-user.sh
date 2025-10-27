#!/bin/bash

# Multi-User Integration Test Script
# Tests per-user MCP discovery with Arcade integration

echo "═══════════════════════════════════════════════════════════════"
echo "    TEAL AGENTS + ARCADE INTEGRATION TEST"
echo "    Testing: Per-User MCP Discovery (UPGRADE-001)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Configuration
AGENT_URL="http://localhost:8000/integration-test-agent/1.0"
TEST_API_KEY="test-api-key-12345"

# Test users (DummyAuthorizer will extract from Bearer token)
ALICE_TOKEN="Bearer alice@test.com"
BOB_TOKEN="Bearer bob@test.com"
CHARLIE_TOKEN="Bearer charlie@test.com"

# Results directory
RESULTS_DIR="TEST-integration/results"
mkdir -p "$RESULTS_DIR"

echo "📋 Test Configuration"
echo "───────────────────────────────────────────────────────────────"
echo "Agent URL: $AGENT_URL"
echo "Test Users: alice@test.com, bob@test.com, charlie@test.com"
echo "Results Dir: $RESULTS_DIR"
echo ""

# Function to test a user
test_user() {
    local user_name=$1
    local auth_token=$2
    local result_file="$RESULTS_DIR/${user_name}-response.json"
    
    echo "🧪 Testing User: $user_name"
    echo "───────────────────────────────────────────────────────────────"
    
    # Send request
    curl -X POST "$AGENT_URL" \
        -H "Content-Type: application/json" \
        -H "Authorization: $auth_token" \
        -H "X-API-Key: $TEST_API_KEY" \
        -d '{
            "items": [
                {
                    "content_type": "text",
                    "content": "What tools do you have? List all available tools."
                }
            ]
        }' \
        -s -o "$result_file"
    
    if [ $? -eq 0 ]; then
        echo "✅ Request successful"
        echo "📄 Response saved to: $result_file"
        
        # Extract some info
        if command -v jq &> /dev/null; then
            echo "📊 Response status: $(cat $result_file | jq -r '.status // "N/A"')"
            echo "📊 Session ID: $(cat $result_file | jq -r '.session_id // "N/A"')"
            echo "📊 Task ID: $(cat $result_file | jq -r '.task_id // "N/A"')"
        fi
    else
        echo "❌ Request failed"
    fi
    
    echo ""
}

# Check if server is running
echo "🔍 Checking if server is running..."
# Check if server is responding (any response means it's up)
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:8000/ 2>/dev/null)
if [ -z "$HTTP_CODE" ] || [ "$HTTP_CODE" = "000" ]; then
    echo "❌ Server not responding at http://localhost:8000"
    echo ""
    echo "Please start the server first:"
    echo "  cd TEST-integration"
    echo "  ./start-server.sh"
    echo ""
    exit 1
fi
echo "✅ Server is running"
echo ""

# Run tests for each user
echo "🚀 Starting Multi-User Tests"
echo "═══════════════════════════════════════════════════════════════"
echo ""

test_user "alice" "$ALICE_TOKEN"
sleep 2

test_user "bob" "$BOB_TOKEN"
sleep 2

test_user "charlie" "$CHARLIE_TOKEN"

# Summary
echo "═══════════════════════════════════════════════════════════════"
echo "    TEST COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "📊 Results saved in: $RESULTS_DIR"
echo ""
echo "🔍 Next Steps:"
echo "  1. Check server logs for per-user MCP discovery messages"
echo "  2. Compare tool lists between users"
echo "  3. Verify no cross-user contamination"
echo ""
echo "Expected in logs:"
echo "  ✅ 'Starting MCP discovery for user: alice@test.com'"
echo "  ✅ 'Starting MCP discovery for user: bob@test.com'"
echo "  ✅ 'Starting MCP discovery for user: charlie@test.com'"
echo ""
echo "NOT expected in logs:"
echo "  ❌ 'MCP discovery already completed' (for different users)"
echo ""

