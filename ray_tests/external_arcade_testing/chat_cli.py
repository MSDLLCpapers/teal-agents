#!/usr/bin/env python3
"""Scenario stub that delegates to the shared chat CLI."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ray_tests.common.chat_cli import run_cli


if __name__ == "__main__":
    run_cli(Path(__file__).parent.resolve())
