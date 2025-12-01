import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ray_tests.common.test_api_key import test_api_key


if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) < 2:
        print("Usage: python test_api_key.py YOUR_API_KEY_HERE")
        _sys.exit(1)
    test_api_key(_sys.argv[1])
