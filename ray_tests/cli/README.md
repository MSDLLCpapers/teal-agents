# Interactive CLI for Agent Platform

An interactive command-line interface for running AI agents with a session-based workflow.

## Quick Start

### Start a CLI Session

```bash
python -m src.cli examples/sim-real-world/network-rca
```

This will:
1. Load the project configuration
2. Discover and register plugins
3. Load context (runbooks and examples)
4. Start an interactive session

### Interactive Commands

Once in the session, you can use slash commands:

```
agent> /help                  # Show all commands
agent> /status                # Show session status
agent> /settings              # View current settings
agent> /settings hitl_mode=autonomous  # Change HITL mode
agent> /plugins               # List available plugins and tools
agent> /run <task>           # Execute a specific task
agent> /history              # Show task history
agent> /clear                # Clear screen
agent> /exit                 # Exit session
```

### Running Tasks

You can run tasks in two ways:

1. **Using /run command:**
```
agent> /run Investigate Wi-Fi outage on Floor 3
```

2. **Direct input (without /run):**
```
agent> Investigate Wi-Fi outage on Floor 3
```

## Project Structure

A CLI-enabled project should have this structure:

```
my-project/
├── agent_config.yaml         # Project configuration
├── network_rca_plugin.py     # Plugin file (auto-discovered)
├── runbooks.json            # Optional: Domain runbooks
├── examples.json            # Optional: Few-shot examples
├── data/                    # Optional: Project data
│   ├── alerts.json
│   └── metrics.json
└── logs/                    # Auto-created: Execution logs
```

## Configuration File

### Example `agent_config.yaml`

```yaml
project:
  name: "My Agent Project"
  description: "Description of what this agent does"
  version: "1.0.0"

plugins:
  auto_discover: true
  paths:
    - "."  # Look for plugins in current directory

context:
  runbooks: "runbooks.json"
  examples: "examples.json"

settings:
  default_hitl_mode: "guided_automation"
  default_step_budget: 6
  enable_feedback: true
  log_level: "INFO"

data:
  # Optional: Define project-specific data files
  alerts: "data/alerts.json"
  metrics: "data/metrics.json"
```

## Session Settings

Settings can be changed during the session:

### HITL Modes
```
agent> /settings hitl_mode=autonomous         # No approvals
agent> /settings hitl_mode=strategic_review   # Review plans only
agent> /settings hitl_mode=guided_automation  # Plans + high-risk (default)
agent> /settings hitl_mode=manual             # Approve everything
```

### Step Budget
```
agent> /settings step_budget=10  # Allow up to 10 reasoning steps
```

### Feedback
```
agent> /settings feedback=true   # Enable feedback collection
agent> /settings feedback=false  # Disable feedback collection
```

## Example Session

```bash
$ python -m src.cli examples/sim-real-world/network-rca

======================================================================
🤖 Agent Platform Interactive CLI
======================================================================

Loading project from: examples/sim-real-world/network-rca

Initializing agent runtime...

✓ Project: Network RCA Agent
  Wi-Fi root cause analysis agent with diagnostic tools
✓ Loaded 1 plugin(s):
  - NetworkRCA
✓ Runbooks: runbooks.json
✓ Examples: examples.json
✓ Runtime initialized

Current Settings:
  HITL Mode: GUIDED_AUTOMATION
  Step Budget: 6
  Feedback Enabled: True

Type /help for available commands
======================================================================

agent> /plugins

Available Plugins:
============================================================

NetworkRCA:
  - get_alerts                [MEDIUM  ]
  - get_topology              [LOW     ]
  - get_metrics               [MEDIUM  ]
  - get_change_log            [MEDIUM  ]
  - correlate_events          [HIGH    ]
============================================================

agent> Investigate Wi-Fi outage on Floor 3

🚀 Starting task: Investigate Wi-Fi outage on Floor 3...
============================================================

[Task execution with HITL approvals...]

✅ Task completed
Result: Root cause identified - Configuration change on CTRL-WIFI-1 
at 08:05 caused authentication failures on Floor 3 access points.
Steps: 4/4
============================================================

agent> /history

Task History:
============================================================
✓ [1] Investigate Wi-Fi outage on Floor 3 (15.2s, 4 steps)
============================================================

agent> /exit

👋 Goodbye! 1 task(s) completed in this session.
Logs saved to: logs/feedback.jsonl
```

## Architecture

The CLI system consists of:

- **AgentShell**: Main interactive loop
- **AgentSession**: Long-running runtime and state management
- **ProjectLoader**: Auto-discovery of plugins and configuration
- **CommandRegistry**: Slash command system
- **Models**: Configuration and state data structures

## Benefits

1. **No Restart Between Tasks**: Run multiple tasks in one session
2. **Interactive Configuration**: Change settings on-the-fly
3. **Project Isolation**: Each project self-contained
4. **Familiar UX**: Similar to kubectl, docker CLI, etc.
5. **Easy Debugging**: Experiment with different settings quickly

## Creating New Projects

1. Create project directory
2. Add `agent_config.yaml` (optional, defaults work fine)
3. Create plugins (auto-discovered from current directory)
4. Optionally add `runbooks.json` and `examples.json`
5. Run: `python -m src.cli <project-path>`

That's it! The CLI will discover and load everything automatically.
