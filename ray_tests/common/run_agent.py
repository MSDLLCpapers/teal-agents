#!/usr/bin/env python3
"""Shared standalone agent runner. Scenario stubs call run_agent(<scenario_dir>)."""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


def run_agent(project_dir: Path):
    """
    Start the FastAPI server for the agent defined in the scenario directory.

    Args:
        project_dir: Path to a scenario folder containing config.yaml and .env
    """
    script_dir = project_dir.resolve()
    project_root = script_dir.parent.parent  # repo root

    # Warn if virtualenv not active (non-fatal)
    ray_tests_dir = script_dir.parent
    venv_path = ray_tests_dir / ".venv"
    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )
    if not in_venv and venv_path.exists():
        print("=" * 70)
        print("  WARNING: Not running in virtual environment!")
        print("=" * 70)
        print(f"\nVirtual environment detected at: {venv_path}")
        print("Activate it for consistent deps:")
        print(f"  source {venv_path}/bin/activate")
        print()

    # PYTHONPATH setup
    sk_agents_src = project_root / "src" / "sk-agents" / "src"
    shared_utils_src = project_root / "shared" / "ska_utils" / "src"
    for path in (sk_agents_src, shared_utils_src, script_dir):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    # Load scenario env
    env_path = script_dir / ".env"
    load_dotenv(env_path)
    if not env_path.exists():
        print(f"ERROR: .env file not found at {env_path}")
        print("Copy .env.example and fill in required values.")
        sys.exit(1)

    # Basic credential reminder
    api_key = os.getenv("MERCK_API_KEY")
    if not api_key or api_key == "your-x-merck-apikey-here":
        print("WARNING: MERCK_API_KEY not configured in .env file")
        print(f"Edit {env_path} and add your API key")
        print()

    # Work from repo root so relative paths resolve
    os.chdir(project_root)

    print("=" * 70)
    print("  FileAssistant Test Agent - Standalone Runner")
    print("=" * 70)
    print(f"\nWorking Directory: {project_root} (repo root)")
    print(f"Scenario Directory: {script_dir}")
    print(f"Environment File: {env_path}")
    print(f"Config File: {os.getenv('TA_SERVICE_CONFIG')}")
    print(f"Plugin Module: {os.getenv('TA_PLUGIN_MODULE')}")
    print(f"Custom Factory: {os.getenv('TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE')}")
    print(f"API Endpoint: {os.getenv('MERCK_API_ROOT')}")
    print()

    try:
        import uvicorn
        from sk_agents.app import app

        print("=" * 70)
        print("  Starting FastAPI Server")
        print("=" * 70)
        print("\nAgent will be available at:")
        print("  - API Endpoint: http://localhost:8000/FileAssistant/0.1/invoke")
        print("  - Swagger UI: http://localhost:8000/FileAssistant/0.1/docs")
        print("Press Ctrl+C to stop the server")
        print("=" * 70)
        print()

        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            reload=False,
        )
    except Exception as e:
        print(f"ERROR: Failed to start FastAPI server: {e}")
        sys.exit(1)


if __name__ == "__main__":
    run_agent(Path(__file__).parent.resolve())
