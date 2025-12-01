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

### Quick Start

This test agent is now **self-contained** in the `ray_tests/simple_agent_1` directory!

```bash
# 1. Navigate to the test directory
cd ray_tests/simple_agent_1

# 2. Create your .env file
cp .env.example .env

# 3. Edit .env and add your Merck API key
# Update: MERCK_API_KEY=your-actual-x-merck-apikey

# 4. Install dependencies (one-time, from src/sk-agents)
cd ../../src/sk-agents && uv sync && cd ../../ray_tests/simple_agent_1

# 5. Test the integration
python test_merck_integration.py

# 6. Run the agent
python run_agent.py
```

### Detailed Setup

#### 1. Configure Environment

Create a local `.env` file in this directory:

```bash
# From ray_tests/simple_agent_1
cp .env.example .env
```

Edit `.env` and configure your Merck API credentials:

```bash
# All paths are relative to this directory
TA_SERVICE_CONFIG=config.yaml
TA_PLUGIN_MODULE=file_plugin.py
TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE=merck_chat_completion_factory.py
TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME=MerckChatCompletionFactory

# Add your actual Merck API key
MERCK_API_KEY=your-x-merck-apikey-here
MERCK_API_ROOT=https://iapi-test.merck.com/gpt/v2
```

**Note:** This agent uses a **custom LLM integration** for Merck's internal GPT API instead of standard OpenAI endpoints.

#### 2. Install Dependencies

From the `src/sk-agents` directory (only needed once):

```bash
cd ../../src/sk-agents
uv sync  # or: pip install -e .
cd ../../ray_tests/simple_agent_1
```

#### 3. Test the Integration

```bash
python test_merck_integration.py
```

#### 4. Start the Agent

**Option A: Using the standalone runner (recommended)**

```bash
python run_agent.py
```

**Option B: Using FastAPI directly**

```bash
# Make sure your .env is loaded
cd ../../src/sk-agents
cp ../../ray_tests/simple_agent_1/.env .env
fastapi run src/sk_agents/app.py
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
    model: gpt-5-2025-08-07       # Merck's custom model
    plugins:
      - FilePlugin                # Custom plugin
```

### Custom LLM Integration

This agent demonstrates **custom LLM endpoint integration** using Merck's internal GPT API:

#### Components:

1. **`merck_chat_completion.py`** - Custom Semantic Kernel chat completion client
   - Implements `ChatCompletionClientBase` interface
   - Wraps Merck API with async HTTP calls
   - Handles message formatting and response parsing
   - Supports both standard and streaming completions

2. **`merck_chat_completion_factory.py`** - Factory for creating Merck clients
   - Extends `ChatCompletionFactory` abstract class
   - Registers supported models (`gpt-5-2025-08-07`, etc.)
   - Provides configuration requirements (API key, endpoint)
   - Instantiates `MerckChatCompletion` clients

#### Integration Flow:

```
ChatCompletionBuilder → MerckChatCompletionFactory → MerckChatCompletion → Merck API
```

The platform automatically:
1. Detects custom factory via environment variables
2. Uses factory to create chat completion clients
3. Routes all LLM calls through your custom endpoint

This pattern allows **any LLM endpoint** to be integrated without modifying platform code.

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
