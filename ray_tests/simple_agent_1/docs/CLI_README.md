# FileAssistant Interactive CLI

A streamlined interactive CLI for chatting with the FileAssistant agent, with live streaming responses.

## Features

- ✨ **Direct Agent Invocation** - Bypasses FastAPI for direct TealAgentsV1Alpha1Handler access
- 🔄 **Live Streaming** - Real-time response streaming with Rich terminal formatting
- 💬 **Session Management** - Maintains conversation context across messages
- 🎨 **Beautiful UI** - Markdown rendering and colored output
- 🔧 **Simple Commands** - `/help`, `/clear`, `/new`, `/exit`

## Quick Start

### 1. Activate Virtual Environment

```bash
cd ray_tests
source .venv/bin/activate  # or test_env/bin/activate
```

### 2. Navigate to Project

```bash
cd simple_agent_1
```

### 3. Run the CLI

```bash
python chat_cli.py
```

## Usage

### Chat with the Agent

Just type your message and press Enter:

```
💬 You: List all files in the data directory

🤖 FileAssistant
┌─────────────────────────────────────────┐
│ Here are the files in the data         │
│ directory:                              │
│                                         │
│ 1. meeting_notes.md                    │
│ 2. notes.json                          │
│ 3. sample.txt                          │
└─────────────────────────────────────────┘
```

### Commands

- `/exit` or `/quit` - Exit the CLI
- `/clear` - Clear the screen
- `/new` - Start a new session (clears chat history)
- `/help` - Show help message

### Example Queries

```
> List all files
> Read sample.txt
> Find all JSON files
> What's in meeting_notes.md?
> Search for files with "meeting" in the name
```

## Architecture

```
chat_cli.py
    ↓
agent_client.py (DirectAgentClient)
    ↓
TealAgentsV1Alpha1Handler
    ↓
AgentBuilder → KernelBuilder → FilePlugin
    ↓
Merck Chat Completion API
```

### Key Components

1. **chat_cli.py** - Interactive REPL with Rich UI
2. **agent_client.py** - Direct handler wrapper with streaming
3. **config.yaml** - Agent configuration (model, system prompt, plugins)
4. **.env** - Environment variables (API keys, paths)

## Configuration

The CLI reads from:
- `config.yaml` - Agent configuration
- `.env` - Environment variables

### Important Settings in config.yaml

```yaml
spec:
  agent:
    model: gpt-5-2025-08-07
    reasoning_effort: low
    plugins:
      - FilePlugin
```

## Troubleshooting

### Module Import Errors

Make sure you're in the virtual environment:
```bash
source ../test_env/bin/activate
```

### Agent Not Using Tools

Check the logs during initialization - you should see:
- "Created KernelBuilder"
- "Created AgentBuilder"
- "Created TealAgentsV1Alpha1Handler"

Enable debug logging in `chat_cli.py`:
```python
logging.basicConfig(level=logging.DEBUG)
```

### API Errors

Verify your `.env` file has the correct:
- `MERCK_API_KEY`
- `MERCK_API_ROOT`
- All absolute paths for plugins and config

## Advantages over FastAPI

1. **Debugging** - Direct access to handler, easier to add logging
2. **Performance** - No HTTP serialization overhead
3. **Streaming** - Native async streaming without SSE complexity
4. **MCP Support** - Better control over OAuth flows
5. **Development** - Faster iteration, no server restart needed

## Next Steps

- Test the agent's tool usage (FilePlugin)
- Add MCP server support
- Implement HITL approvals if needed
- Add command history persistence

## Comparison

| Feature | FastAPI + Swagger | CLI |
|---------|------------------|-----|
| Interface | Web browser | Terminal |
| Streaming | SSE | Native async |
| Setup | Server + requests | Direct invocation |
| Debugging | HTTP logs | Direct logs |
| Speed | HTTP overhead | Direct calls |
| Tools | Swagger UI | Rich terminal |

## Files

```
simple_agent_1/
├── chat_cli.py          # Interactive CLI (run this)
├── agent_client.py      # Direct handler wrapper
├── config.yaml          # Agent configuration
├── .env                 # Environment variables
├── file_plugin.py       # FilePlugin implementation
├── data/                # Test data
│   ├── meeting_notes.md
│   ├── notes.json
│   └── sample.txt
└── CLI_README.md        # This file
