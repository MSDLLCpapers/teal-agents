# Quick Start Guide - FileAssistant Test Agent

Get up and running in 5 minutes!

## TL;DR

```bash
# 1. Setup virtual environment (one-time)
cd ray_tests
./setup_venv.sh

# 2. Activate venv and configure
source .venv/bin/activate
cd simple_agent_1
cp .env.example .env
# Edit .env and add your MERCK_API_KEY

# 3. Test and run
python test_merck_integration.py  # Test it works
python run_agent.py               # Run the agent
```

Visit: http://localhost:8000/FileAssistant/0.1/docs

## Step-by-Step

### 1. Setup Virtual Environment (2 minutes, one-time)

```bash
# Navigate to ray_tests directory
cd ray_tests

# Run the setup script
./setup_venv.sh
```

This creates a shared virtual environment at `ray_tests/.venv` and installs all dependencies.

### 2. Configure Environment (1 minute)

```bash
# Activate the virtual environment
source .venv/bin/activate

# Navigate to test agent
cd simple_agent_1

# Create local .env file
cp .env.example .env

# Edit .env with your API key
nano .env  # or vim, code, etc.
```

In `.env`, update:
```bash
MERCK_API_KEY=your-actual-x-merck-apikey-here
```

### 3. Test Integration (1 minute)

```bash
# Make sure venv is activated!
python test_merck_integration.py
```

Should see:
```
✓ All tests PASSED! Integration is working correctly.
```

### 4. Run Agent (1 minute)

```bash
# Venv should still be activated
python run_agent.py
```

**Note:** The scripts will warn you if the virtual environment isn't activated.

### 5. Try It Out!

Open browser to: http://localhost:8000/FileAssistant/0.1/docs

Try this request:
```json
{
  "input": "What files are in the data directory?"
}
```

## Common Commands

```bash
# Activate virtual environment (do this first!)
cd ray_tests
source .venv/bin/activate

# Then run tests
cd simple_agent_1
python test_merck_integration.py

# Run the agent
python run_agent.py

# Test with curl
curl -X POST "http://localhost:8000/FileAssistant/0.1/invoke" \
  -H "Content-Type: application/json" \
  -d '{"input": "List all files"}'

# When done, deactivate
deactivate
```

## File Structure

```
ray_tests/simple_agent_1/
├── .env                    # Your local config (create from .env.example)
├── .env.example            # Template
├── config.yaml             # Agent configuration
├── file_plugin.py          # Custom plugin
├── merck_chat_completion.py          # Custom LLM client
├── merck_chat_completion_factory.py  # Factory
├── run_agent.py            # Standalone agent runner
├── test_merck_integration.py         # Integration tests
├── data/                   # Test data files
├── README.md               # Full documentation
├── SETUP_GUIDE.md          # Detailed setup guide
└── QUICK_START.md          # This file
```

## Troubleshooting

**Problem:** "MERCK_API_KEY not configured"
**Solution:** Edit `.env` and add your actual API key

**Problem:** "ModuleNotFoundError" or import errors
**Solution:** 
1. Make sure venv is activated: `source ray_tests/.venv/bin/activate`
2. Check installation: `pip list | grep sk-agents`
3. Re-run setup if needed: `cd ray_tests && ./setup_venv.sh`

**Problem:** "WARNING: Not running in virtual environment"
**Solution:** Activate it: `cd ray_tests && source .venv/bin/activate`

**Problem:** Tests fail with API errors
**Solution:** Check your API key is valid and you have network access to Merck API

## What's Different?

This test directory is now **self-contained**:
- ✅ Local `.env` file (no need to edit files in `src/sk-agents`)
- ✅ Standalone runner (`run_agent.py`)
- ✅ All paths relative to this directory
- ✅ Run everything from here - no `cd` gymnastics!

## Next Steps

- Read [README.md](README.md) for full documentation
- Check [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed instructions
- Review [INTEGRATION_SUMMARY.md](INTEGRATION_SUMMARY.md) for technical details
- Modify `config.yaml` to customize the agent
- Add your own plugins and tools!

## Need Help?

- Check the full [README.md](README.md)
- Review [SETUP_GUIDE.md](SETUP_GUIDE.md)
- Look at error messages in the terminal
- Verify your `.env` configuration
