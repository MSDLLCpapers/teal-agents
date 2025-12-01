# Teal Agents Test Suite

This directory contains test agents and examples for the Teal Agents platform.

## Shared Virtual Environment

All test agents in this directory share a common Python virtual environment located at `ray_tests/.venv`. This approach:

- ✅ Avoids dependency conflicts
- ✅ Provides consistent environment across all tests
- ✅ Makes setup simple and reproducible
- ✅ Reduces disk space (one venv vs many)

## Quick Setup

```bash
cd ray_tests
./setup_venv.sh
```

This will:
1. Create a Python virtual environment at `.venv`
2. Install all required dependencies
3. Install `sk-agents` and `ska-utils` in editable mode

## Using the Virtual Environment

### Activate the environment

```bash
# From ray_tests directory
source .venv/bin/activate

# Now you can run any test agent
cd simple_agent_1
python run_agent.py
python test_merck_integration.py
```

### Deactivate when done

```bash
deactivate
```

### Auto-detection

The test scripts (`run_agent.py`, `test_merck_integration.py`) will automatically detect if you're not in the virtual environment and provide helpful messages.

## Directory Structure

```
ray_tests/
├── .venv/                  # Shared virtual environment (created by setup)
├── requirements.txt        # Dependencies for all test agents
├── setup_venv.sh          # Setup script (run this first)
├── README.md              # This file
├── simple_agent_1/        # Test agent 1: FileAssistant with Merck API
│   ├── .env               # Local configuration
│   ├── run_agent.py       # Run the agent
│   ├── test_merck_integration.py  # Integration tests
│   └── ...
└── (future test agents will be added here)
```

## Test Agents

### simple_agent_1 - FileAssistant

A basic test agent demonstrating:
- Custom plugin development (FilePlugin)
- Custom LLM integration (Merck API)
- Self-contained test structure
- FastAPI REST endpoint

See [simple_agent_1/README.md](simple_agent_1/README.md) for details.

## Adding New Test Agents

To add a new test agent:

1. **Create a new directory** under `ray_tests/`
2. **Use the shared venv** - no need to create a new one
3. **Follow the pattern** from `simple_agent_1/`
4. **Update this README** with a link to your agent

## Dependencies

The shared virtual environment includes:

- **sk-agents** - Core agent framework (editable install)
- **ska-utils** - Shared utilities (editable install)
- **httpx** - Async HTTP client
- **python-dotenv** - Environment configuration
- **uvicorn** - ASGI server
- **fastapi** - Web framework
- And all their dependencies

See [requirements.txt](requirements.txt) for the complete list.

## Troubleshooting

### Setup fails

**Problem:** `./setup_venv.sh` fails
**Solution:** 
- Ensure Python 3.12+ is installed: `python3 --version`
- Check permissions: `chmod +x setup_venv.sh`
- Run with bash explicitly: `bash setup_venv.sh`

### Import errors

**Problem:** `ModuleNotFoundError` when running tests
**Solution:**
- Make sure venv is activated: `source .venv/bin/activate`
- Check if dependencies installed: `pip list | grep sk-agents`
- Re-run setup: `./setup_venv.sh`

### Virtual environment not detected

**Problem:** Scripts don't detect the venv
**Solution:**
- Activate manually: `source .venv/bin/activate`
- Check path: `which python` (should point to `.venv/bin/python`)

## Manual Setup (Alternative)

If you prefer manual setup or the script doesn't work:

```bash
cd ray_tests

# Create venv
python3 -m venv .venv

# Activate
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt
```

## Maintenance

### Update dependencies

To add or update dependencies:

1. Edit `requirements.txt`
2. Activate venv: `source .venv/bin/activate`
3. Install: `pip install -r requirements.txt`

### Rebuild venv

To completely rebuild the virtual environment:

```bash
cd ray_tests
rm -rf .venv
./setup_venv.sh
```

## Related Documentation

- [Main Teal Agents README](../README.md)
- [sk-agents Documentation](../src/sk-agents/README.md)
- [simple_agent_1 Documentation](simple_agent_1/README.md)
