# Application State After Phases 1 & 2: Foundation for Human-in-the-Loop Implementation

This document provides a comprehensive overview of the application state after completing Phases 1 and 2, as described in `01-02-state-refactor-implementation-plan.md` and `02-02-manual-tool-call-implementation-plan.md`. This overview is intended to support Phase 3 planning, which will introduce Human-in-the-Loop (HITL) functionality for selected tool calls.

## New Infrastructure Components

### Authorization System
The application now includes a pluggable authorization system:

- **`src/sk_agents/authorization/` module** - Complete authorization infrastructure
- **`RequestAuthorizer`** - Abstract base class requiring `authorize_request(auth_header: str) -> str`
- **`DummyAuthorizer`** - Development implementation returning 'dummyuser' for all requests
- **`AuthorizerFactory`** - Thread-safe singleton factory with environment variable configuration
    - `TA_AUTHORIZER_MODULE` - Module path for authorization implementation
    - `TA_AUTHORIZER_CLASS` - Class name for authorization implementation
- **Error handling** - Comprehensive handling for import failures and misconfigurations

### Persistence System
A pluggable state storage system is now available:

- **`src/sk_agents/persistence/` module** - Complete persistence infrastructure
- **`TaskPersistenceManager`** - Abstract base class with CRUD operations for `AgentTask` objects
    - `create(task: AgentTask) -> None`
    - `load(task_id: str) -> AgentTask | None`
    - `update(task: AgentTask) -> None`
    - `delete(task_id: str) -> None`
- **`InMemoryPersistenceManager`** - Thread-safe in-memory implementation with proper locking
- **`PersistenceFactory`** - Environment variable configuration
    - `TA_PERSISTENCE_MODULE` - Module path for persistence implementation
    - `TA_PERSISTENCE_CLASS` - Class name for persistence implementation
- **Error handling** - Persistence failures result in 5xx responses

### State Models
New data models support complete conversation state management:

- **`AgentTask`** - Core state container with:
    - `task_id`, `session_id`, `user_id` for identification
    - `items: list[AgentTaskItem]` for conversation history
    - `created_at`, `last_updated_at` timestamps
    - `status: Literal["Running", "Paused", "Completed", "Failed"]` for state tracking
- **`AgentTaskItem`** - Individual conversation entries with:
    - `role: Literal["user", "assistant"]` for message attribution
    - `item: MultiModalItem` for content
    - `request_id: str` for tracking individual requests
    - `updated: datetime` for chronological ordering
- **`UserMessage`** - Input model with optional state identifiers:
    - `session_id: str | None` for session continuity
    - `task_id: str | None` for task resumption
    - `items: list[MultiModalItem]` for multimodal content
- **`TealAgentsResponse`/`TealAgentsPartialResponse`** - Response models with:
    - `session_id`, `task_id`, `request_id` for complete state tracking
    - `output` field (collapsed from previous `output_raw`/`output_pydantic`)
    - All existing response fields preserved

## New API Architecture

### Module Structure
A completely isolated API version has been created:

- **`src/sk_agents/tealagents/`** - Top-level module, completely isolated from `skagents`
- **`src/sk_agents/tealagents/v1alpha1/`** - Version-specific implementation
- **`src/sk_agents/tealagents/v1alpha1/handler.py`** - Core handler implementation
- **`src/sk_agents/tealagents/v1alpha1/agent.py`** - LLM interaction and tool call
- **Isolation requirements**:
    - No imports from `skagents` modules in `tealagents` modules
    - No shared mutable state between API versions
    - Separate error handling paths to prevent cross-contamination
    - Independent configuration validation logic

### Routing Integration
The application routing has been extended to support the new API:

- **Updated `routes.py`** - Detects `tealagents` as first token in `apiVersion`
- **New `AppV3` class** - Follows existing `AppV1`/`AppV2` patterns
- **Main `app.py`** - Routes `tealagents/v1alpha1` configurations to `AppV3`
- **Backward compatibility** - All existing API versions continue to work unchanged

## Tool Call Interception Architecture

### HITL Foundation
The groundwork for Human-in-the-Loop functionality has been established:

- **`src/sk_agents/hitl/hitl_manager.py`** - Placeholder module with interception point
- **`check_for_intervention(tool_call: FunctionCallContent) -> bool`** - Core interception function
    - Currently returns `False` (no intervention) for all tool calls
    - Establishes the exact point where HITL logic will be implemented
    - Receives complete `FunctionCallContent` objects for inspection

### Manual Tool Orchestration
The `Agent` (`src/sk_agents/tealagents/v1alpha1/agent.py`) implements the tool invocation loop:

- **Direct LLM interaction** - Uses `ChatCompletionClientBase` instead of high-level agent methods
- **Manual tool extraction** - Extracts `FunctionCallContent` objects from LLM responses
- **Clear interception point** - Each tool call is individually passed to `hitl_manager.check_for_intervention()`
- **Parallel execution** - Approved tool calls are executed via `asyncio.gather()`
- **Recursive handling** - Supports multi-turn tool calling scenarios
- **Streaming support** - Both `invoke()` and `invoke_stream()` methods have identical interception logic

## State Management Flow

### Request Processing Pipeline
The `TealAgentsV1Alpha1Handler` (`src/sk_agents/tealagents/v1alpha1/handler.py`) processes requests with a clear state management flow:

1. **Authorization** - Via pluggable authorizer (extracts `user_id`)
2. **Session/Task ID handling** - Generation or validation of state identifiers
3. **User ownership verification** - Existing tasks checked for user ownership
4. **Chat history reconstruction** - Built from persisted `AgentTaskItem` objects
5. **Agent invocation** - Invoke agent with appropriate chat history
6. **State persistence** - After each interaction
7. **Response generation** - With complete state identifiers

### Concurrency & Error Handling
Robust error handling and concurrency support:

- **Thread-safe state access** - Proper locking mechanisms in persistence layer
- **Comprehensive error responses**:
    - 401 for authorization failures
    - 404 for missing tasks
    - 5xx for persistence failures
- **Streaming support** - State management with keepalive mechanisms
- **Race condition handling** - Concurrent access to same task properly managed

## Key Architectural Decisions for Phase 3

### Tool Call Interception Points
The architecture provides clear interception capabilities:

- **Identical interception logic** - Both `invoke()` and `invoke_stream()` methods have the same interception flow
- **Pre-execution inspection** - Tool calls are extracted and inspected before execution
- **Individual tool processing** - Each `FunctionCallContent` object is individually passed to the interception function
- **Execution control** - The interception point can prevent tool execution (currently always allows)

### State Persistence Capabilities
Complete state management for paused/resumed operations:

- **Full conversation history** - Maintained in `AgentTask.items` with chronological ordering
- **Unique request tracking** - Each interaction has a unique `request_id`
- **Pause support** - Task status field supports "Paused" state (designed for HITL)
- **Timestamp tracking** - All state objects include timestamps for timeout/cleanup logic
- **User association** - All tasks are associated with specific users for authorization

### Response Model Design
Response models are designed to support HITL workflows:

- **State identifier inclusion** - All responses include `session_id`, `task_id`, `request_id`
- **Streaming consistency** - State identifiers maintained throughout streaming responses
- **Extensibility** - Response models designed to support future HITL-specific fields
- **Client tracking** - State identifiers allow clients to track and respond to approval requests

## HITL Implementation Ready Points

The architecture establishes the following foundation for Phase 3 HITL implementation:

### 1. Tool Call Interception

- **`hitl_manager.check_for_intervention()`** - Ready to implement policy-based tool approval
- **Complete tool context** - `FunctionCallContent` objects provide full tool information
- **Execution control** - Return `True` to block tool execution

### 2. State Persistence for Paused Tasks

- **Task pausing** - Change `AgentTask.status` to "Paused"
- **Conversation state** - Complete chat history preserved for resumption
- **User context** - User authorization preserved for approval requests

### 3. Response Mechanisms

- **State tracking** - Response models include all necessary identifiers
- **Client communication** - Mechanisms exist to inform clients of approval requirements
- **Resumption support** - Task can be resumed with `request_id` in subsequent requests

### 4. Authorization Integration

- **User identification** - Every request tied to specific user
- **Approval tracking** - Tool approval requests can be associated with users
- **Security** - User ownership verification prevents unauthorized task access

## Environment Variables

New environment variables introduced:

- `TA_AUTHORIZER_MODULE` - Module path for authorization implementation
- `TA_AUTHORIZER_CLASS` - Class name for authorization implementation
- `TA_PERSISTENCE_MODULE` - Module path for persistence implementation
- `TA_PERSISTENCE_CLASS` - Class name for persistence implementation

**Default values for development:**

- Authorizer: `sk_agents.authorization.dummy_authorizer.DummyAuthorizer`
- Persistence: `sk_agents.persistence.in_memory_persistence_manager.InMemoryPersistenceManager`

## Backward Compatibility

The application maintains complete backward compatibility:

- **Existing APIs unchanged** - `skagents/v1` and `skagents/v2alpha1` continue to work
- **No shared state** - New `tealagents` API is completely isolated
- **Configuration compatibility** - Existing configuration files continue to work
- **Telemetry preservation** - All existing telemetry functionality maintained

## Summary

After Phases 1 and 2, the application provides a complete foundation for Human-in-the-Loop implementation with:

1. **Authorization infrastructure** - User identification and request authorization
2. **State persistence** - Complete conversation state management with pause/resume capability
3. **Tool call interception** - Clear points for inspecting and controlling tool execution
4. **Response mechanisms** - State tracking and client communication capabilities
5. **Isolation** - New functionality completely isolated from existing APIs

The `tealagents/v1alpha1` API path now provides stateful, interceptable agent interactions while maintaining complete backward compatibility with existing functionality. Phase 3 can build upon this foundation to implement Human-in-the-Loop approval workflows for selected tool calls.
