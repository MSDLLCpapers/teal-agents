# Restructuring Notes - Self-Contained Test Directory

This document explains the changes made to make the test directory self-contained.

## What Changed

### Before (Original Structure)

```
teal-agents/
├── src/sk-agents/
│   └── .env  ← Configuration file here
└── ray_tests/simple_agent_1/
    ├── config.yaml
    ├── file_plugin.py
    └── ... (test files)
```

**Issues:**
- Configuration split across directories
- Had to run agent from `src/sk-agents` directory
- Paths in `.env` were relative to `src/sk-agents`
- Not self-contained or portable

### After (Self-Contained Structure)

```
teal-agents/
├── src/sk-agents/
│   └── .env  ← Can be deleted (optional)
└── ray_tests/simple_agent_1/
    ├── .env  ← New! Local configuration
    ├── run_agent.py  ← New! Standalone runner
    ├── test_merck_integration.py  ← Updated to use local .env
    ├── config.yaml
    ├── file_plugin.py
    ├── merck_chat_completion.py
    ├── merck_chat_completion_factory.py
    ├── QUICK_START.md  ← New! Quick reference
    └── ... (other files)
```

**Benefits:**
- ✅ Everything in one directory
- ✅ Can run from test directory
- ✅ Self-contained and portable
- ✅ Easier to understand and maintain

## Files Modified

### 1. Created: `.env`
- **Location:** `ray_tests/simple_agent_1/.env`
- **Purpose:** Local environment configuration
- **Changes:** All paths now relative to test directory
  - `TA_SERVICE_CONFIG=config.yaml` (was `../../ray_tests/simple_agent_1/config.yaml`)
  - `TA_PLUGIN_MODULE=file_plugin.py` (was `../../ray_tests/simple_agent_1/file_plugin.py`)
  - `TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE=merck_chat_completion_factory.py`

### 2. Created: `run_agent.py`
- **Location:** `ray_tests/simple_agent_1/run_agent.py`
- **Purpose:** Standalone agent runner
- **Features:**
  - Loads local `.env` file
  - Sets up Python paths automatically
  - Changes to test directory
  - Starts FastAPI server
  - Made executable with `chmod +x`

### 3. Updated: `test_merck_integration.py`
- **Changes:**
  - Now loads `.env` from test directory (not `src/sk-agents/.env`)
  - Updated Python path setup
  - Error messages reference local `.env` location

### 4. Updated: `.env.example`
- **Changes:**
  - Updated comments to indicate local usage
  - Changed all paths to be relative to test directory

### 5. Updated: `README.md`
- **Changes:**
  - Added "Quick Start" section
  - Updated setup instructions for self-contained structure
  - Documented `run_agent.py` usage
  - Simplified workflow

### 6. Updated: `SETUP_GUIDE.md`
- **Changes:**
  - Updated all paths and commands
  - Emphasized local `.env` file
  - Added `run_agent.py` instructions
  - Updated troubleshooting for new structure

### 7. Created: `QUICK_START.md`
- **Location:** `ray_tests/simple_agent_1/QUICK_START.md`
- **Purpose:** Ultra-fast getting started guide
- **Features:**
  - 5-minute setup
  - Copy-paste commands
  - Common troubleshooting

## Migration Guide

### For Existing Users

If you were using the old structure:

1. **Your old `.env` file** at `src/sk-agents/.env` can stay (won't interfere)
2. **Create new local `.env`:**
   ```bash
   cd ray_tests/simple_agent_1
   cp .env.example .env
   # Add your MERCK_API_KEY
   ```
3. **Use new runner:**
   ```bash
   python run_agent.py
   ```

### What to Keep

- ✅ Keep both `.env` files if you want (they don't conflict)
- ✅ Old method still works (running from `src/sk-agents`)
- ✅ New method is just more convenient

### What to Clean Up (Optional)

If you want to fully migrate:

1. Delete `src/sk-agents/.env` (optional)
2. Use only `ray_tests/simple_agent_1/.env`
3. Always run from test directory

## Usage Examples

### Old Way (Still Works)
```bash
cd src/sk-agents
# Edit .env with complex relative paths
fastapi run src/sk_agents/app.py
```

### New Way (Recommended)
```bash
cd ray_tests/simple_agent_1
# Edit .env with simple local paths
python run_agent.py
```

## Technical Details

### How `run_agent.py` Works

1. **Path Setup:**
   ```python
   SCRIPT_DIR = Path(__file__).parent.resolve()
   PROJECT_ROOT = SCRIPT_DIR.parent.parent
   
   # Add to Python path
   sys.path.insert(0, str(PROJECT_ROOT / "src" / "sk-agents" / "src"))
   sys.path.insert(0, str(PROJECT_ROOT / "shared" / "ska_utils" / "src"))
   sys.path.insert(0, str(SCRIPT_DIR))
   ```

2. **Environment Loading:**
   ```python
   env_path = SCRIPT_DIR / ".env"
   load_dotenv(env_path)
   ```

3. **Working Directory:**
   ```python
   os.chdir(SCRIPT_DIR)
   ```

4. **Server Start:**
   ```python
   uvicorn.run(app, host="0.0.0.0", port=8000)
   ```

### Relative Path Resolution

With working directory in test folder:
- `config.yaml` → `ray_tests/simple_agent_1/config.yaml`
- `file_plugin.py` → `ray_tests/simple_agent_1/file_plugin.py`
- `merck_chat_completion_factory.py` → `ray_tests/simple_agent_1/merck_chat_completion_factory.py`

The platform's module loader handles these paths correctly because we `chdir()` to the test directory.

## Benefits Summary

### Developer Experience
- 🎯 Single directory focus
- 📁 All files in one place
- 🚀 Quick to start
- 📝 Simpler documentation

### Maintainability
- 🔧 Easier to modify
- 🐛 Easier to debug
- 📦 Easier to share
- 🧪 Easier to test

### Portability
- 📂 Self-contained
- 🔄 Easy to copy/move
- 🎁 Easy to package
- 👥 Easy to share with team

## Future Considerations

This self-contained pattern can be applied to:
- Other test agents (simple_agent_2, simple_agent_3, etc.)
- Example projects
- Tutorial materials
- Template repositories

## Rollback

If you need to revert to the old structure:

1. Delete `ray_tests/simple_agent_1/.env`
2. Delete `ray_tests/simple_agent_1/run_agent.py`
3. Use the old `.env` at `src/sk-agents/.env`
4. Run from `src/sk-agents` directory

The integration files (merck_chat_completion.py, etc.) work with both approaches.
