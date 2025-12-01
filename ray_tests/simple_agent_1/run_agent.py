#!/usr/bin/env python3
"""
Standalone agent runner for FileAssistant test agent.

This script allows you to run the agent directly from the test directory
without needing to cd into src/sk-agents.

Usage:
    python run_agent.py

Or make it executable and run:
    chmod +x run_agent.py
    ./run_agent.py
"""

import os
import sys
from pathlib import Path

# Get the directory containing this script
SCRIPT_DIR = Path(__file__).parent.resolve()

# Project root is two levels up from ray_tests/simple_agent_1
PROJECT_ROOT = SCRIPT_DIR.parent.parent

# Check if we're running in the virtual environment
RAY_TESTS_DIR = SCRIPT_DIR.parent
VENV_PATH = RAY_TESTS_DIR / ".venv"
IN_VENV = hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)

if not IN_VENV and VENV_PATH.exists():
    print("=" * 70)
    print("  WARNING: Not running in virtual environment!")
    print("=" * 70)
    print(f"\nVirtual environment detected at: {VENV_PATH}")
    print("\nPlease activate it first:")
    print(f"  source {VENV_PATH}/bin/activate")
    print(f"  python {Path(__file__).name}")
    print("\nOr if you haven't set it up yet:")
    print(f"  cd {RAY_TESTS_DIR}")
    print("  ./setup_venv.sh")
    print("=" * 70)
    sys.exit(1)
elif not IN_VENV:
    print("=" * 70)
    print("  NOTE: Virtual environment not found")
    print("=" * 70)
    print(f"\nFor better dependency management, set up a virtual environment:")
    print(f"  cd {RAY_TESTS_DIR}")
    print("  ./setup_venv.sh")
    print("\nContinuing without virtual environment...")
    print("=" * 70)
    print()

# Add sk-agents source to Python path
SK_AGENTS_SRC = PROJECT_ROOT / "src" / "sk-agents" / "src"
sys.path.insert(0, str(SK_AGENTS_SRC))

# Add shared utilities to Python path
SHARED_SRC = PROJECT_ROOT / "shared" / "ska_utils" / "src"
sys.path.insert(0, str(SHARED_SRC))

# Add test directory to Python path (for imports of merck_chat_completion, etc.)
sys.path.insert(0, str(SCRIPT_DIR))

# Load environment variables from local .env file
from dotenv import load_dotenv
env_path = SCRIPT_DIR / ".env"
load_dotenv(env_path)

# Verify .env file exists and is loaded
if not env_path.exists():
    print(f"ERROR: .env file not found at {env_path}")
    print("\nPlease create a .env file in this directory.")
    print("You can copy .env.example and update with your credentials:")
    print(f"  cp {SCRIPT_DIR}/.env.example {env_path}")
    sys.exit(1)

# Check for API key
api_key = os.getenv("MERCK_API_KEY")
if not api_key or api_key == "your-x-merck-apikey-here":
    print("WARNING: MERCK_API_KEY not configured in .env file")
    print(f"Please edit {env_path} and add your actual Merck API key")
    print()

# Change working directory to project root
# The platform's module loader expects to run from project root
os.chdir(PROJECT_ROOT)

print("=" * 70)
print("  FileAssistant Test Agent - Standalone Runner")
print("=" * 70)
print(f"\nWorking Directory: {PROJECT_ROOT} (project root)")
print(f"Test Directory: {SCRIPT_DIR}")
print(f"Environment File: {env_path}")
print(f"Config File: {os.getenv('TA_SERVICE_CONFIG')}")
print(f"Plugin Module: {os.getenv('TA_PLUGIN_MODULE')}")
print(f"Custom Factory: {os.getenv('TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE')}")
print(f"API Endpoint: {os.getenv('MERCK_API_ROOT')}")
print()

# Now import and run the FastAPI app
try:
    import uvicorn
    from sk_agents.app import app
    
    print("=" * 70)
    print("  Starting FastAPI Server")
    print("=" * 70)
    print("\nAgent will be available at:")
    print("  - API Endpoint: http://localhost:8000/FileAssistant/0.1/invoke")
    print("  - Swagger UI: http://localhost:8000/FileAssistant/0.1/docs")
    print("\nPress Ctrl+C to stop the server")
    print("=" * 70)
    print()
    
    # Run the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    
except KeyboardInterrupt:
    print("\n\nServer stopped by user")
    sys.exit(0)
except ImportError as e:
    print(f"\nERROR: Failed to import required modules: {e}")
    print("\nMake sure dependencies are installed:")
    print("  cd ../../src/sk-agents")
    print("  uv sync")
    sys.exit(1)
except Exception as e:
    print(f"\nERROR: Failed to start agent: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
