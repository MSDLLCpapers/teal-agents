# Human-in-the-Loop (HITL) System

This document provides a comprehensive overview of the Human-in-the-Loop (HITL) system for the Teal Agents framework, including detailed documentation of all classes, functions, and implementation patterns.

## Overview

The HITL system provides a security and governance layer that enables human oversight and approval for high-risk or sensitive tool calls before they are executed by AI agents. This system ensures that potentially dangerous operations require explicit human authorization, adding a critical safety layer to autonomous agent execution.

### Core Features

- **Tool Call Interception**: Automatic detection and interception of high-risk function calls
- **Policy-Based Governance**: Integration with plugin catalog for configurable tool governance
- **Exception-Based Flow Control**: Clean exception handling for intervention requirements
- **Request Tracking**: Full traceability of intervention requests and responses
- **URL-Based Approval**: RESTful approval/rejection mechanism for human reviewers

## Folder Structure

```text
hitl/
├── __init__.py                    # Package initialization (empty)
├── README.md                      # This documentation file
└── hitl_manager.py               # Core HITL functionality and exception handling
```

## Core Classes and Functions Documentation

### 1. check_for_intervention() Function

**File**: `hitl_manager.py`

The primary function responsible for determining whether a tool call requires human intervention.

#### Function Signature

```python
def check_for_intervention(tool_call: FunctionCallContent) -> bool
```

#### Parameters

- **`tool_call: FunctionCallContent`**: A Semantic Kernel function call object containing:
  - `plugin_name`: The name of the plugin containing the function
  - `function_name`: The specific function being called
  - Additional metadata about the function call

#### Returns

- **`bool`**: `True` if the tool call requires human intervention, `False` otherwise

#### Implementation Details

The function performs the following operations:

1. **Plugin Catalog Integration**: Creates a `PluginCatalogFactory` instance to access the tool governance catalog
2. **Tool Identification**: Constructs a unique tool ID using the format `{plugin_name}-{function_name}`
3. **Governance Check**: Queries the catalog for the tool's governance settings
4. **Policy Evaluation**: Returns the value of `tool.governance.requires_hitl` if the tool is found in the catalog
5. **Fallback Behavior**: Returns `False` (no intervention required) if:
   - The catalog is not configured
   - The tool is not found in the catalog

::: sk_agents.hitl.hitl_manager.check_for_intervention

#### Usage in Agent Workflow

This function is called by the agent handler during tool call processing:

```python
# In agent handler
for fc in function_calls:
    if hitl_manager.check_for_intervention(fc):
        intervention_calls.append(fc)

if intervention_calls:
    raise hitl_manager.HitlInterventionRequired(intervention_calls)
```

#### Debug Output

The function includes diagnostic logging that outputs:

- The tool ID being checked
- Whether HITL intervention is required for that tool

### 2. HitlInterventionRequired Exception

**File**: `hitl_manager.py`

A custom exception class that signals when tool calls require human intervention and halts agent execution until approval is received.

#### Class Definition

```python
class HitlInterventionRequired(Exception):
    def __init__(self, function_calls: list[FunctionCallContent])
```

#### Attributes

- **`function_calls: list[FunctionCallContent]`**: List of all function calls that require intervention
- **`plugin_name: str`**: Name of the plugin from the first function call (for convenience)
- **`function_name: str`**: Name of the function from the first function call (for convenience)

#### Constructor Behavior

1. **Stores Function Calls**: Preserves the complete list of function calls requiring intervention
2. **Extracts Metadata**: Sets `plugin_name` and `function_name` from the first function call for easy access
3. **Generates Message**: Creates a descriptive error message indicating which plugin and function requires intervention
4. **Handles Empty Lists**: Provides a fallback message if no function calls are provided

#### Exception Message Format

- **With function calls**: `"HITL intervention required for {plugin_name}.{function_name}"`
- **Without function calls**: `"HITL intervention required"`

#### Usage in Error Handling

The exception is caught by agent handlers to generate `HitlResponse` objects:

```python
try:
    # Agent execution code
    pass
except hitl_manager.HitlInterventionRequired as hitl_exc:
    # Generate HITL response with approval/rejection URLs
    return HitlResponse(
        task_id=task_id,
        session_id=session_id,
        request_id=request_id,
        tool_calls=[fc.model_dump() for fc in hitl_exc.function_calls],
        approval_url=f"/approve/{request_id}",
        rejection_url=f"/reject/{request_id}"
    )
```

::: sk_agents.hitl.hitl_manager.HitlInterventionRequired

## Integration with Teal Agents Framework

### Agent Handler Integration

The HITL system is integrated into the main agent execution flow at multiple points:

1. **Import**: `from sk_agents.hitl import hitl_manager`
2. **Tool Call Screening**: Each function call is checked before execution
3. **Exception Handling**: HITL exceptions are caught and converted to HTTP responses
4. **State Management**: HITL requests are tracked through the agent's state system

### Plugin Catalog Dependency

The HITL system relies on the plugin catalog for governance policies:

- **Tool Registration**: Tools must be registered in the catalog with governance metadata
- **Policy Configuration**: The `requires_hitl` flag in tool governance determines intervention requirements
- **Dynamic Updates**: Governance policies can be updated without code changes

### Response Model Integration

The system generates `HitlResponse` objects (defined in `sk_agents.tealagents.models`) containing:

- **Task Metadata**: `task_id`, `session_id`, `request_id`
- **Human Message**: Descriptive message about the intervention requirement
- **Approval URLs**: RESTful endpoints for human approval/rejection
- **Tool Call Data**: Serialized function calls awaiting approval

## Security Considerations

### Fail-Safe Design

- **Default Deny**: Unknown tools default to no intervention (configurable)
- **Catalog Dependency**: Missing catalog configuration falls back to permissive behavior
- **Exception Isolation**: HITL exceptions don't crash the agent, they pause execution

### Governance Integration

- **Centralized Policy**: All governance rules are managed through the plugin catalog
- **Audit Trail**: All intervention requests are tracked and logged
- **Configurable Risk Levels**: Tools can be classified with different risk levels and policies

## Future Enhancements

### Planned Features

- **Risk Level Classification**: Support for different intervention policies based on risk levels
- **Batch Approval**: Ability to approve/reject multiple tool calls simultaneously
- **Timeout Handling**: Automatic rejection of approval requests after timeout
- **User Context**: Integration with user authentication for personalized approval flows

### Extension Points

- **Custom Policies**: Support for custom intervention logic beyond simple boolean flags
- **Approval Workflows**: Integration with enterprise approval systems
- **Notification Systems**: Email/Slack notifications for pending approvals
- **Analytics**: Metrics on intervention frequency and approval rates

## Error Handling

### Exception Hierarchy

```text
Exception
└── HitlInterventionRequired
    ├── function_calls: list[FunctionCallContent]
    ├── plugin_name: str
    └── function_name: str
```

### Error Recovery

- **Graceful Degradation**: System continues operation even if HITL components fail
- **Logging**: All intervention decisions are logged for audit purposes
- **Fallback Behavior**: Clear fallback policies when governance data is unavailable

## Testing Considerations

### Unit Testing

- **Mock Plugin Catalog**: Test with various catalog configurations
- **Exception Flow**: Verify exception handling and response generation
- **Edge Cases**: Test with empty function call lists and missing catalog data

### Integration Testing

- **End-to-End Flow**: Test complete approval/rejection workflows
- **State Persistence**: Verify that HITL requests are properly tracked
- **URL Generation**: Validate approval/rejection URL correctness

## Development Guidelines

### Adding New HITL Policies

1. **Register Tools**: Add tools to the plugin catalog with appropriate governance flags
2. **Test Integration**: Verify that `check_for_intervention` correctly identifies the tools
3. **Update Documentation**: Document new governance policies and their implications

### Debugging HITL Issues

1. **Check Logs**: Look for "HITL Check: Intercepted call" messages
2. **Verify Catalog**: Ensure the plugin catalog is properly configured
3. **Test Isolation**: Use unit tests to isolate HITL logic from agent execution
