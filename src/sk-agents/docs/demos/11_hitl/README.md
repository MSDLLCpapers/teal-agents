# Human-in-the-Loop (HITL) Agent Demo

This demo showcases how to configure an agent with **Human-in-the-Loop (HITL)** capabilities, which allows you to require human approval before sensitive or high-risk plugin functions are executed by the AI agent.

## Overview

Human-in-the-Loop is a critical security and governance feature that enables:

- **Risk Mitigation**: Prevent potentially dangerous operations from executing without human oversight
- **Compliance**: Meet regulatory requirements for human approval on sensitive data operations
- **Security**: Add a safety layer between AI decision-making and critical actions
- **Auditability**: Track and approve all high-risk operations with full traceability

## How HITL Works

1. **Agent Execution**: The agent processes a user request and determines it needs to call a plugin function
2. **Governance Check**: The framework checks the plugin catalog to see if the function requires HITL approval
3. **Execution Pause**: If HITL is required, execution halts and returns an `HitlResponse` with approval URLs
4. **Human Review**: A human reviewer examines the function call details and either approves or rejects it
5. **Execution Resume**: If approved, the agent resumes and executes the function; if rejected, the agent is notified

## Configuration Components

### 1. Agent Configuration (`config.yaml`)

The agent configuration defines the agent's behavior and which plugins it has access to:

```yaml
apiVersion: tealagents/v1alpha1
kind: Chat
description: >
  A simple Hello World agent that greets users with their user ID from the user context
name: MathAgent
version: 0.1
spec:
  agent:
    name: default
    role: MathAgent
    model: gpt-4o-2024-05-13
    system_prompt: >
        Your task is to provide a help with Math problems, and invoke the plugin
        when you finish the math problem before responding
    plugins:
        - sensitive_plugin
```

**Key Elements:**
- `apiVersion`: Uses `tealagents/v1alpha1` which supports HITL features
- `kind`: Set to `Chat` for conversational agents
- `plugins`: Lists the plugins available to the agent (in this case, `sensitive_plugin`)
- `system_prompt`: Instructs the agent when to use the plugin

### 2. Custom Plugin Implementation (`custom_plugins.py`)

Define your plugin with functions that may require human oversight:

```python
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from sk_agents.ska_types import BasePlugin


class sensitive_plugin(BasePlugin):
    @kernel_function(description="invoke when a math problem is solved")
    def delete_user_data(self):
        return "you shouldnt see me"
```

**Key Elements:**
- **Inherit from `BasePlugin`**: Ensures proper integration with the framework
- **`@kernel_function` decorator**: Marks methods as callable by the agent
- **Function description**: Tells the agent when to invoke this function
- **Function logic**: The actual operation that will execute after approval

### 3. Plugin Catalog Configuration (`catalog.json`)

The plugin catalog is where you define governance rules, including HITL requirements:

```json
{
  "plugins": [
    {
      "plugin_id": "sensitive_plugin",
      "name": "sensitive_plugin",
      "description": "Executes shell commands.",
      "version": "1.0",
      "owner": "system",
      "plugin_type": { "type_name": "code" },
      "tools": [
        {
          "tool_id": "sensitive_plugin-delete_user_data",
          "name": "delete_user_data",
          "description": "Executes a command in the shell to delete user.",
          "governance": {
            "requires_hitl": true,
            "cost": "high",
            "data_sensitivity": "sensitive"
          },
          "auth": null
        }
      ]
    }
  ]
}
```

**Key Elements:**
- **`plugin_id`**: Must match the plugin class name in your `custom_plugins.py`
- **`tool_id`**: Format is `{plugin_id}-{function_name}` (e.g., `sensitive_plugin-delete_user_data`)
- **`governance`**: Defines the governance controls for this tool
  - **`requires_hitl: true`**: Enables human-in-the-loop for this function
  - **`cost`**: Resource classification (`low`, `medium`, `high`)
  - **`data_sensitivity`**: Sensitivity level (`public`, `proprietary`, `confidential`, `sensitive`)
- **`auth`**: Optional authentication requirements (null in this example)

## Environment Configuration

To run this demo, you need to configure the following environment variables:

```bash
# API Key for LLM access
TA_API_KEY=<your-API-key>

# Path to your agent configuration
TA_SERVICE_CONFIG=demos/11_hitl/config.yaml

# Path to your custom plugin implementation
TA_PLUGIN_MODULE=demos/11_hitl/custom_plugins.py

# Path to the plugin catalog (defines HITL governance)
TA_PLUGIN_CATALOG_MODULE=src/sk_agents/plugin_catalog/local_plugin_catalog.py
TA_PLUGIN_CATALOG_CLASS=FileBasedPluginCatalog
TA_PLUGIN_CATALOG_PATH=src/sk_agents/plugin_catalog/catalog.json
```

**Important Notes:**
- The `TA_PLUGIN_CATALOG_PATH` should point to your `catalog.json` file
- You can create custom catalog implementations by extending the `PluginCatalog` abstract class
- The catalog is loaded as a singleton, so all agents in the application share the same governance rules

## HITL Workflow Example

### Step 1: Initial Request

User sends a request to the agent:

```json
POST /MathAgent/0.1
{
  "user_id": "user123",
  "input": "What is 5 + 3? After you solve it, delete my data."
}
```

### Step 2: Agent Processing

The agent:
1. Solves the math problem (5 + 3 = 8)
2. Determines it needs to call `delete_user_data`
3. Checks the plugin catalog and finds `requires_hitl: true`
4. Raises an `HitlInterventionRequired` exception

### Step 3: HITL Response

The framework returns a `HitlResponse` instead of executing the function:

```json
{
  "task_id": "task_abc123",
  "session_id": "session_xyz789",
  "request_id": "req_def456",
  "human_message": "HITL intervention required for sensitive_plugin.delete_user_data",
  "tool_calls": [
    {
      "plugin_name": "sensitive_plugin",
      "function_name": "delete_user_data",
      "arguments": {}
    }
  ],
  "approval_url": "/approve/req_def456",
  "rejection_url": "/reject/req_def456"
}
```

### Step 4: Human Review

A human reviewer examines the function call details and makes a decision.

**To Approve:**
```bash
POST /approve/req_def456
{
  "action": "approved",
  "reason": "User requested data deletion, verified identity"
}
```

**To Reject:**
```bash
POST /reject/req_def456
{
  "action": "rejected",
  "reason": "Insufficient verification"
}
```

### Step 5: Resume Execution

After approval/rejection, use the resume endpoint:

```bash
POST /resume/req_def456
{
  "action_status": "approved"  # or "rejected"
}
```

If approved, the agent executes `delete_user_data` and completes the response.
If rejected, the agent is informed the action was not allowed and responds accordingly.

## Governance Options

The `governance` object in the plugin catalog supports multiple control mechanisms:

### HITL Requirement
```json
"governance": {
  "requires_hitl": true  // Set to false to allow automatic execution
}
```

### Cost Classification
Used for resource tracking and budgeting:
```json
"governance": {
  "cost": "high"  // Options: "low", "medium", "high"
}
```

### Data Sensitivity
Used for data governance and compliance:
```json
"governance": {
  "data_sensitivity": "sensitive"
  // Options: "public", "proprietary", "confidential", "sensitive"
}
```

## Common Use Cases

### 1. Financial Transactions
```json
{
  "tool_id": "finance_plugin-initiate_transfer",
  "governance": {
    "requires_hitl": true,
    "cost": "high",
    "data_sensitivity": "sensitive"
  }
}
```

### 2. System Administration
```json
{
  "tool_id": "admin_tools-shutdown_service",
  "governance": {
    "requires_hitl": true,
    "cost": "high",
    "data_sensitivity": "confidential"
  }
}
```

### 3. Data Deletion
```json
{
  "tool_id": "sensitive_plugin-delete_user_data",
  "governance": {
    "requires_hitl": true,
    "cost": "medium",
    "data_sensitivity": "sensitive"
  }
}
```

### 4. Low-Risk Operations
```json
{
  "tool_id": "finance_plugin-get_balance",
  "governance": {
    "requires_hitl": false,  // No human approval needed
    "cost": "low",
    "data_sensitivity": "proprietary"
  }
}
```

## Best Practices

### 1. Plugin Naming Conventions
- Use descriptive plugin IDs that indicate their purpose
- Keep function names clear and action-oriented
- Tool IDs must follow the format: `{plugin_id}-{function_name}`

### 2. Governance Configuration
- Mark all destructive operations as `requires_hitl: true`
- Set appropriate cost and sensitivity levels
- Document governance decisions in plugin descriptions

### 3. System Prompts
- Clearly instruct the agent when to use HITL-protected functions
- Provide context about why certain operations require approval
- Set expectations for users about approval workflows

### 4. Error Handling
- Always handle HITL responses in your client application
- Provide clear UI for approval/rejection workflows
- Implement timeout handling for pending approvals

### 5. Audit Trail
- Log all HITL intervention requests
- Track approval/rejection decisions with timestamps and reasons
- Maintain records for compliance requirements

## Architecture Integration

The HITL system integrates with several framework components:

1. **Plugin Catalog (Singleton)**: Centralized governance rules
2. **HITL Manager**: Checks for intervention requirements
3. **Agent Handler**: Catches HITL exceptions and generates responses
4. **Persistence Layer**: Tracks task state during approval workflows
5. **REST API**: Provides approval/rejection endpoints

## Troubleshooting

### HITL Not Triggering

**Problem**: Function executes without requiring approval

**Solutions**:
- Verify `requires_hitl: true` is set in `catalog.json`
- Confirm `tool_id` matches the format: `{plugin_id}-{function_name}`
- Check that `TA_PLUGIN_CATALOG_PATH` points to the correct catalog file
- Ensure the plugin catalog is properly loaded (check logs)

### Tool Not Found in Catalog

**Problem**: Tool is not recognized by the catalog

**Solutions**:
- Verify the `plugin_id` matches your plugin class name
- Check the `tool_id` format is correct
- Ensure the catalog JSON is valid (use a JSON validator)
- Restart the service after updating the catalog

### Approval URLs Not Working

**Problem**: Approval/rejection endpoints return errors

**Solutions**:
- Confirm the request ID is valid and not expired
- Check that persistence is configured correctly
- Verify the resume endpoint is being called properly
- Review service logs for detailed error messages

## Further Reading

- [HITL System Documentation](../../hitl/hitl.md)
- [Plugin Catalog Documentation](../../hitl/plugin_catalog.md)
- [Persistence Management](../../hitl/persistence.md)
- [Authorization & Auth Storage](../../hitl/authorization.md)
