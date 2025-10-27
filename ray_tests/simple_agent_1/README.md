# Simple Agent 1: File Assistant

A simple chat agent that demonstrates the Teal Agents framework with a custom local plugin for file operations.

## Purpose

This agent serves as a basic test case for the Teal Agents platform, demonstrating:
- Agent configuration using `tealagents/v1alpha1` API
- Custom plugin development (FilePlugin)
- Local file access and manipulation
- LLM-orchestrated tool usage

## Agent Capabilities

The FileAssistant can:
1. **List files** - Show all files in the data directory
2. **Read files** - Read and display file contents
3. **Search files** - Find files using patterns (e.g., `*.json`, `*.txt`)

## File Structure

```
simple_agent_1/
├── config.yaml          # Agent configuration
├── file_plugin.py       # Custom FilePlugin implementation
├── .env.example         # Environment configuration template
├── data/                # Sample data files
│   ├── sample.txt       # Plain text file
│   ├── notes.json       # JSON data file
│   └── meeting_notes.md # Markdown file
└── README.md            # This file
```

## Setup

### 1. Configure Environment

Copy the `.env.example` file to `.env` in the project root:

```bash
cd /path/to/teal-agents/src/sk-agents
cp tests/ray_tests/simple_agent_1/.env.example .env
```

Edit `.env` and add your OpenAI API key:

```bash
TA_API_KEY=sk-your-actual-api-key-here
TA_SERVICE_CONFIG=tests/ray_tests/simple_agent_1/config.yaml
TA_PLUGIN_MODULE=tests/ray_tests/simple_agent_1/file_plugin.py
```

### 2. Install Dependencies

Ensure you have Python 3.12+ and all dependencies installed:

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### 3. Start the Agent

Run the agent using FastAPI:

```bash
# From the sk-agents directory
fastapi run src/sk_agents/app.py
```

Or using uv:

```bash
uv run -- fastapi run src/sk_agents/app.py
```

The agent will start on `http://localhost:8000`

## Usage

### Access the API Documentation

Open your browser to:
```
http://localhost:8000/FileAssistant/0.1/docs
```

This provides an interactive Swagger UI for testing the agent.

### REST API Endpoint

The agent exposes a REST endpoint at:
```
POST http://localhost:8000/FileAssistant/0.1/invoke
```

### Example Requests

#### 1. List All Files

**Request:**
```json
{
  "input": "What files are available in the data directory?"
}
```

**Expected Response:**
The agent will use the `list_files` tool and respond with information about all files in the data directory.

#### 2. Read a Specific File

**Request:**
```json
{
  "input": "Read the contents of sample.txt"
}
```

**Expected Response:**
The agent will use the `read_file` tool to retrieve and display the file contents.

#### 3. Search for Files

**Request:**
```json
{
  "input": "Show me all JSON files"
}
```

**Expected Response:**
The agent will use the `search_files` tool with pattern `*.json` to find matching files.

#### 4. Complex Query

**Request:**
```json
{
  "input": "Can you read the meeting notes and summarize the action items?"
}
```

**Expected Response:**
The agent will:
1. Use `search_files` to find `meeting_notes.md`
2. Use `read_file` to get its contents
3. Analyze and summarize the action items using the LLM

## Architecture

### Agent Configuration (`config.yaml`)

```yaml
apiVersion: tealagents/v1alpha1  # Uses AppV3
kind: Chat                       # Chat-style agent
name: FileAssistant
spec:
  agent:
    model: gpt-4o-mini            # LLM model
    plugins:
      - FilePlugin                # Custom plugin
```

### Plugin Implementation (`file_plugin.py`)

The FilePlugin implements three kernel functions:
- `list_files()` - Returns `FileListResult` with all files
- `read_file(filename)` - Returns `FileContent` with file data
- `search_files(pattern)` - Returns `FileListResult` with matches

All functions return structured Pydantic models for reliable parsing.

## Testing

### Manual Testing

1. Start the agent
2. Visit the Swagger UI at `/FileAssistant/0.1/docs`
3. Try the example requests above
4. Verify the agent correctly uses the file tools

### Expected Behavior

- Agent should automatically invoke file tools when asked about files
- Responses should be natural and include file information
- Error handling should be graceful (e.g., file not found)

## Next Steps

This agent demonstrates local plugins. Future agents in the ray_tests suite will:

1. **simple_agent_2** - Add MCP server integration
2. **simple_agent_3** - Test OAuth2 authentication with MCP
3. **simple_agent_4** - Test governance and HITL requirements
4. **simple_agent_5** - Multi-task sequential agents

## Troubleshooting

### Agent doesn't start
- Check that `.env` file exists in the sk-agents root directory
- Verify `TA_API_KEY` is set correctly
- Ensure paths in `TA_SERVICE_CONFIG` and `TA_PLUGIN_MODULE` are correct

### Tools not being called
- Check that FilePlugin is properly loaded (see startup logs)
- Verify the system prompt encourages tool usage
- Try more explicit requests (e.g., "Use the list_files tool")

### File operations fail
- Ensure the `data/` directory exists with sample files
- Check file permissions
- Review error messages in agent logs

## Related Documentation

- [Main README](../../../README.md) - Teal Agents overview
- [Plugin Guide](../../../docs/demos/03_plugins/README.md) - Creating custom plugins
- [Chat Agents](../../../docs/demos/09_chat_simple/README.md) - Chat agent configuration
- [MCP Tests](../../mcp/README.md) - MCP unit and integration tests
