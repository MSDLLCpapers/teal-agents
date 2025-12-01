"""Entry point for interactive CLI.

Usage:
    python -m src.cli <project-path>
"""

import asyncio
import logging
import sys
from pathlib import Path

from src.cli.agent_shell import AgentShell


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.cli <project-path>")
        print("\nExample:")
        print("  python -m src.cli examples/network-rca")
        sys.exit(1)

    project_path = Path(sys.argv[1])

    if not project_path.exists():
        print(f"Error: Project path does not exist: {project_path}")
        sys.exit(1)

    if not project_path.is_dir():
        print(f"Error: Project path is not a directory: {project_path}")
        sys.exit(1)

    # Setup minimal logging (session will configure based on project config)
    logging.basicConfig(
        level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    # Start shell
    shell = AgentShell(project_path)
    asyncio.run(shell.start())


if __name__ == "__main__":
    main()
