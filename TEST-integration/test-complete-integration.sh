#!/bin/bash
# Complete End-to-End Integration Test
# Tests: Entra ID SSO + Per-User Discovery + Arcade Integration

echo "═══════════════════════════════════════════════════════════════"
echo "    COMPLETE TEAL AGENTS + ARCADE INTEGRATION TEST"
echo "    Testing: All 3 Auth Layers + Per-User Multi-Tenant"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Configuration
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"
RESULTS_DIR="$SCRIPT_DIR/results"
mkdir -p "$RESULTS_DIR"

# Test configurations
API_KEY_CONFIG="test-agent-config.yaml"  # Current Arcade
HYBRID_CONFIG="test-hybrid-arcade-config.yaml"  # Both modes

echo "📋 Test Configuration"
echo "───────────────────────────────────────────────────────────────"
echo "Project Root: $PROJECT_ROOT"
echo "Results Dir: $RESULTS_DIR"
echo "API Key Config: $API_KEY_CONFIG"
echo "Hybrid Config: $HYBRID_CONFIG"
echo ""

# Function to check if server is running
check_server() {
    local max_attempts=30
    local attempt=1
    
    echo "🔍 Waiting for server to start..."
    while [ $attempt -le $max_attempts ]; do
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:8000/ 2>/dev/null)
        if [ ! -z "$HTTP_CODE" ] && [ "$HTTP_CODE" != "000" ]; then
            echo "✅ Server is running (HTTP $HTTP_CODE)"
            return 0
        fi
        echo "   Attempt $attempt/$max_attempts..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "❌ Server failed to start after $max_attempts attempts"
    return 1
}

# Function to stop server
stop_server() {
    echo ""
    echo "🛑 Stopping server..."
    pkill -f "fastapi dev" || true
    sleep 2
}

# Function to test with config
test_with_config() {
    local config_name=$1
    local test_label=$2
    
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo "    TEST: $test_label"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    
    # Stop any running server
    stop_server
    
    # Start server with this config
    echo "🚀 Starting server with $config_name..."
    cd "$PROJECT_ROOT/src/sk-agents"
    
    if [ ! -d ".venv" ]; then
        echo "❌ Virtual environment not found!"
        return 1
    fi
    
    source .venv/bin/activate
    export $(cat "$SCRIPT_DIR/.env.test" | grep -v '^#' | xargs)
    export TA_SERVICE_CONFIG="../../TEST-integration/$config_name"
    
    # Start server in background
    fastapi dev src/sk_agents/app.py > "$RESULTS_DIR/server-$test_label.log" 2>&1 &
    SERVER_PID=$!
    
    # Wait for server
    if ! check_server; then
        echo "❌ Server failed to start. Check logs: $RESULTS_DIR/server-$test_label.log"
        kill $SERVER_PID 2>/dev/null || true
        return 1
    fi
    
    # Run multi-user test
    cd "$SCRIPT_DIR"
    echo ""
    echo "🧪 Running multi-user tests..."
    ./test-multi-user.sh
    
    # Copy results
    cp results/*.json "$RESULTS_DIR/${test_label}-" 2>/dev/null || true
    
    # Stop server
    kill $SERVER_PID 2>/dev/null || true
    sleep 2
    
    echo ""
    echo "✅ Test complete: $test_label"
    echo "   Results: $RESULTS_DIR/"
    echo "   Logs: $RESULTS_DIR/server-$test_label.log"
}

# Test 1: Current Arcade (API Key Mode)
test_with_config "$API_KEY_CONFIG" "api-key-mode"

# Test 2: Hybrid Mode (API Key + OAuth fields configured)
test_with_config "$HYBRID_CONFIG" "hybrid-mode"

# Final Summary
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "    ALL TESTS COMPLETE"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "📊 Results Summary:"
echo "  - API Key Mode: $RESULTS_DIR/api-key-mode-*"
echo "  - Hybrid Mode: $RESULTS_DIR/hybrid-mode-*"
echo ""
echo "📋 Server Logs:"
echo "  - API Key: $RESULTS_DIR/server-api-key-mode.log"
echo "  - Hybrid: $RESULTS_DIR/server-hybrid-mode.log"
echo ""
echo "🔍 Next Steps:"
echo "  1. Check server logs for MCP discovery messages"
echo "  2. Verify per-user tool isolation"
echo "  3. Compare API key vs hybrid mode results"
echo ""
echo "Expected in logs:"
echo "  ✅ 'Injected Arcade-User-Id header: alice@test.com'"
echo "  ✅ 'Injected Arcade-User-Id header: bob@test.com'"
echo "  ✅ 'Using OAuth token...' (hybrid mode, if OAuth token available)"
echo "  ✅ 'Using static auth if configured' (if no OAuth token)"
echo ""

