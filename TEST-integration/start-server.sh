#!/bin/bash

# Start Teal Agents server with test configuration

echo "═══════════════════════════════════════════════════════════════"
echo "    STARTING TEAL AGENTS SERVER (TEST MODE)"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
# Navigate to project root (parent of TEST-integration)
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

cd "$PROJECT_ROOT/src/sk-agents"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Run 'uv sync' first."
    exit 1
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Load test environment
echo "🔧 Loading test environment..."
export $(cat "$PROJECT_ROOT/TEST-integration/.env.test" | grep -v '^#' | xargs)

# Check for OpenAI API key
if [ "$OPENAI_API_KEY" == "your-openai-key-here" ]; then
    echo "❌ ERROR: Please set your actual OPENAI_API_KEY in TEST-integration/.env.test"
    exit 1
fi

echo "✅ Environment loaded"
echo ""
echo "📋 Configuration:"
echo "  Agent Config: $TA_SERVICE_CONFIG"
echo "  Authorizer: $TA_AUTHORIZER_CLASS"
echo "  State: $TA_STATE_MANAGEMENT"
echo "  MCP Plugins: $ENABLE_MCP_PLUGINS"
echo ""

# Start server
echo "🚀 Starting FastAPI server..."
echo "   Server will be available at: http://localhost:8000"
echo "   Agent endpoint: http://localhost:8000/integration-test-agent/1.0"
echo "   Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop the server"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Start with reload for development
fastapi dev src/sk_agents/app.py

