# FileAssistant CLI - Usage Guide

## Quick Start

```bash
cd ray_tests/simple_agent_1
source ../test_env/bin/activate
python chat_cli.py
```

## Commands

### Basic Commands

- `/help` - Show help message with all commands
- `/plugins` - List all available tools
- `/new` - Start a new session (clears chat history)
- `/clear` - Clear the screen
- `/exit` or `/quit` - Exit the CLI

### Direct Tool Calling with `@`

Call tools directly without using the LLM:

```bash
# List all files
@FilePlugin.list_files

# Read a specific file
@FilePlugin.read_file filename="sample.txt"

# Search for files
@FilePlugin.search_files pattern="*.json"
```

**Syntax:** `@PluginName.function_name arg1="value1" arg2="value2"`

### Cancellation

- Press **Ctrl+C** during agent streaming to cancel the response
- Shows partial response received before cancellation
- Returns to prompt without exiting CLI

## Available Tools

### FilePlugin

1. **list_files()**
   - Lists all files in the data directory
   - No parameters required
   - Usage: `@FilePlugin.list_files`

2. **read_file(filename: str)**
   - Reads the contents of a specific file
   - Required parameter: `filename` (string)
   - Usage: `@FilePlugin.read_file filename="sample.txt"`

3. **search_files(pattern: str)**
   - Searches for files matching a pattern (supports wildcards)
   - Required parameter: `pattern` (string)
   - Usage: `@FilePlugin.search_files pattern="*.json"`

## Current Configuration

- **Model:** gpt-5-2025-08-07 (o1-style reasoning model)
- **Reasoning Effort:** low
- **API:** Merck Internal GPT API
- **Data Directory:** `ray_tests/simple_agent_1/data/`

## Important Notes

### Tool Usage Patterns

**Option 1: Direct Tool Calling (Recommended for now)**
Use `@` commands to call tools directly:
```
@FilePlugin.list_files
@FilePlugin.read_file filename="meeting_notes.md"
```
This bypasses the LLM and directly invokes the tool function.

**Option 2: Agent-Driven (Automatic)**
Ask the agent in natural language:
```
List all files in the data directory
```

**Note:** gpt-5 (o1-style) models may not support automatic function calling the same way as GPT-4 models. If the agent doesn't use tools automatically, use the `@` commands instead.

### Model Availability

- ✅ **gpt-5-2025-08-07** - Available, working
- ✅ **gpt-4o-mini** - Should work (not tested)
- ❌ **gpt-4o** - Returns 404 (not deployed on Merck API)
- ❌ **gpt-4o-2024-05-13** - Not in supported models list

Check `merck_chat_completion_factory.py` `_MERCK_MODELS` list for supported models.

## Examples

### Example 1: List Files
```
💬 You: @FilePlugin.list_files

📋 Result: FilePlugin.list_files
files=[
  FileInfo(name='meeting_notes.md', path='data/meeting_notes.md', size=1067, extension='.md'),
  FileInfo(name='notes.json', path='data/notes.json', size=858, extension='.json'),
  FileInfo(name='sample.txt', path='data/sample.txt', size=548, extension='.txt')
] 
total_count=3
```

### Example 2: Read File
```
💬 You: @FilePlugin.read_file filename="sample.txt"

📋 Result: FilePlugin.read_file
This is a sample text file for testing the FileAssistant agent.

It contains some basic text that can be read and analyzed.
...
```

### Example 3: Search Files
```
💬 You: @FilePlugin.search_files pattern="*.md"

📋 Result: FilePlugin.search_files
files=[FileInfo(name='meeting_notes.md', ...)] total_count=1
```

### Example 4: Chat with Agent
```
💬 You: List all files

🤖 FileAssistant
[Agent response - may or may not use tools depending on model capabilities]
```

## Debugging

### Enable Debug Logging

Edit `chat_cli.py` line 32:
```python
logging.basicConfig(
    level=logging.INFO,  # Change from WARNING to INFO or DEBUG
    ...
)
```

### Check What's Happening

The logs will show:
- Plugin loading
- Tool registration
- API calls
- Function invocations

## Architecture

```
chat_cli.py (Interactive Shell)
    ↓
agent_client.py (DirectAgentClient)
    ↓
TealAgentsV1Alpha1Handler
    ↓
AgentBuilder → Kernel → FilePlugin
    ↓
MerckChatCompletion → Merck API
```

## Features

✅ **Live Streaming** - Real-time response display
✅ **Session Management** - Maintain context across messages
✅ **Tool Introspection** - `/plugins` shows available tools
✅ **Direct Tool Calling** - `@` commands bypass LLM
✅ **Cancellation** - Ctrl+C stops responses gracefully
✅ **Rich Terminal UI** - Markdown rendering, colors, panels

## Troubleshooting

### Issue: Model Not Found (404)

**Symptom:** `404 Resource Not Found` for model URL

**Solution:** Use a model that's deployed on the Merck API:
- Change `model:` in `config.yaml` to `gpt-5-2025-08-07`
- Or check with Merck team which models are available

### Issue: Agent Not Using Tools

**Symptom:** Agent gives generic advice instead of calling tools

**Workaround:** Use `@` commands to call tools directly:
```
@FilePlugin.list_files
@FilePlugin.read_file filename="sample.txt"
```

**Root Cause:** gpt-5 (o1-style) models may have different function calling behavior than GPT-4 models.

### Issue: Import Errors

**Solution:** Make sure you're in the virtual environment:
```bash
cd ray_tests
source test_env/bin/activate
cd simple_agent_1
```

## Next Steps

1. **Test with gpt-5** - Try chatting after switching back
2. **Request gpt-4o deployment** - Ask Merck team to deploy gpt-4o if needed
3. **Use @ commands** - For reliable tool usage
4. **Add MCP servers** - Ready for MCP plugin integration
