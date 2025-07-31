# Phase 1 - State Refactoring of Teal Agents - Agent component

## Objective
The Agent component of Teal Agents was originally designed to be completely
stateless.  Each invocation accepted a list of "Chat History" messages which
were to contain the entirety of the conversation, thus far. While this would be
ideal to maintain, we have reached a point in its evolution where we will have
to pivot and begin maintaining state in order to support more complex use cases
(e.g. HITL and Authorization for tool use). The purpose of this document is to
provide an overview and required context which should be considered while
designing the implementation of state for this Agent component.

When refactoring, the API version which should act as the base pattern for the
new capability should be `skagents/v2alpha1`. The configuration file structure
should remain the same, but the new API version should be called
`tealagents/v1alpha1`.

## Core Concepts
To enable stateful agent invocation, we will need to introduce three new
concepts in to the agent invocation flow: Session, Task, and Request.

### 1. Session ID (S)
- **Purpose**: Represents the highest-level grouping, corresponding to a continuous interaction or "conversation" with a client.
- **Scope**: It logically groups together multiple related tasks initiated by a user. For example, a user's entire interaction with a chatbot for a specific purpose would be one session.
- **Relevance**: While not directly used for the internal mechanics of agent/orchestrator state, it provides the essential client-facing context and allows clients to manage and reference logical units of work.
- **Lifecycle**: Sessions persist across multiple tasks and can span extended periods of user interaction.

### 2. Task ID (T)
- **Purpose**: Represents a single, stateful "job" or goal that the system is asked to accomplish. A task can be simple (a single agent invocation) or complex (an orchestration involving multiple agents and sub-orchestrators).
- **State**: This is the lynchpin of the stateful architecture. The state associated with a Task ID must include:
    - **Interaction History**: A "chat history" or log of all invocations and responses related to the task. This is critical for providing context in follow-on invocations.
    - **Execution Trace**: A record of the steps taken, tools used, and intermediate results generated.
    - **Status**: The current state of the task (e.g., `Running`, `Paused`, `Completed`, `Failed`).
    - **User Identity**: The unique identifier of the user who created the task for authorization purposes.
    - **Timestamps**: Creation time, last updated time, and optional expiration time.
    - **Metadata**: Additional context and configuration data specific to the task.
- **Lifecycle**: A task is created upon the initial invocation and persists until it is fully completed. Follow-on invocations from the client reference the same Task ID to leverage its history and state.
- **Concurrency**: Multiple concurrent access attempts to the same task must be handled safely to prevent data corruption.

### 3. Request ID (R)
- **Purpose**: Represents a single, atomic attempt or invocation within a task. It provides the finest level of granularity for tracking and control.
- **Scope**: A unique Request ID is generated for each invocation of an agent or orchestrator. All actions performed within that invocation, including tool calls, belong to that single Request ID.
- **Criticality for HITL**: The Request ID is the key to enabling HITL. It allows the system to pause not just a general task, but the *specific agent invocation* that requires human approval. This prevents ambiguity and allows for precise control. When a `Resume Handler` approves an action, it targets the specific Request ID.
- **Benefits**:
    - **Idempotency**: If a resume signal is received multiple times, the system can check the status of the Request ID and prevent duplicate execution.
    - **Auditing**: Provides a detailed, auditable log of every single action taken by the system.
    - **Traceability**: Links all telemetry and logging data to specific request instances.

## Example Flow
### New Request
1. An agent receives a request from either a client or an orchestrator that
   may or may not include a "Session ID" but which DOES NOT contain a "Task ID"
2. If not provided, the agent generates a new "Session ID"
3. The agent generates a new "Task ID" and a new "Request ID"
4. The agent persists the request in its state store with the associated "Task ID"
5. The agent builds the appropriate chat history and invokes the LLM
6. The agent receives the response from the LLM and persists this, associated
   with the same "Task ID". For now we'll focus on getting state implemented
   ignore future HITL or authorization requirements.
7. The agent returns the response along with the "Session ID", "Task ID",
   and "Request ID" to the client or orchestrator

### Follow-on Request
1. An agent receives a follow-on request from either a client or an orchestrator
   that includes a "Task ID".
2. The agent generates a new "Request ID"
3. The agent verifies that the requesting identity (user) was the same
   as the one who initiated the task in the first place (if not, 401).
4. The agent retrieves all associated messages with the provided "Task ID",
   builds the chat history (including the newly received message), and invokes
   the LLM."
5. The agent receives the response from the LLM and persists this, associated
   with the same "Task ID".
6. The agent returns the response along with the "Session ID", "Task ID",
   and "Request ID" to the client or orchestrator

## Implementation Requirements

### Application Integration
* The new `tealagents/v1alpha1` API version should follow the same pattern as existing versions:
  * Create an `AppV3` class similar to `AppV1` and `AppV2`
  * Attempt to reuse the existing `routes.py` `get_rest_routes` function if possible by passing appropriate configuration values
  * If reuse is not feasible due to authentication requirements and scope of changes, create new route handling logic that maintains existing capabilities (especially telemetry)
  * Exclude websocket routes (`get_websocket_routes`) from the new version as they are deprecated
* The main `app.py` should detect the new API version and route to `AppV3` accordingly
* Complete isolation from existing API versions to maintain 100% backward compatibility

### Data Models
* Define a new input type called `UserMessage` which:
  * Does NOT inherit from `BaseMultiModalInput` but has a similar structure
  * Contains a list of `MultiModalItem` objects for the current message (text, images, etc.)
  * Removes the `chat_history` field since history is now managed server-side
  * Optionally accepts "Session ID" and "Task ID" parameters
  * Includes proper validation for UUID formats and required fields
  * Should look like: `{ session_id?, task_id?, items: MultiModalItem[] }`
* Implement comprehensive response models that include all state identifiers
* Define state data models for Session, Task, and Request entities with proper relationships and constraints

### Authentication and Authorization
* Implement a robust authentication system using Entra ID app registration:
  * Clients must send authorization tokens with appropriate scopes to access the platform
  * Implement middleware or route-level logic to verify tokens and extract unique user identifiers (OID)
  * Store user identity with persistent tasks for ownership verification
  * Verify user identity on follow-on requests (return 401 if user doesn't match task owner)
* For initial implementation, abstract this logic and provide mock implementations
* This authentication requirement may preclude reusing the existing `routes.py` file
* Plan follow-up tasks for actual Entra ID integration and token validation

### Configuration System
* The new API version is indicated by `apiVersion: tealagents/v1alpha1` in the configuration file
* Configuration file structure remains the same as existing versions (see `demos/ZZ_wikipedia_demo/config.yaml`)

### State Management
* Abstract out the persistence management to support multiple providers
* Implement an in-memory persistence provider for initial testing (no need for actual persistent implementation initially)
* Design for future Redis or DynamoDB implementations
* Include "last updated" timestamps for future cleanup capabilities
* Do not implement automatic cleanup initially - preserve all task data
* Handle concurrent access to the same task safely to prevent data corruption
* State should include sufficient information to rebuild chat history and context

### Error Handling
* Persistence failures should result in 5xx response codes
* Corrupted or inconsistent state data should cause invocation failures with 5xx responses
* Implement appropriate timeout handling for long-running operations
* Consider implementing keepalive mechanisms for SSE streams (similar to previous 30-second dummy events for long LLM calls)
* Provide comprehensive error messages for debugging and troubleshooting

## Implementation Details

### API Version Detection and Routing
* Define a new logic path for API version `tealagents/v1alpha1` following the same pattern as earlier API versions
* The main `app.py` should detect the new `tealagents/v1alpha1` API version and route to the appropriate `AppV3` class
* Complete isolation ensures this new capability doesn't affect existing functionality

### UserMessage Input Model
* Create a new `UserMessage` class that looks similar to `BaseMultiModalInput` but simplified for single-message input
* Structure: Contains a list of `MultiModalItem` objects (content_type and content) for the current message
* Optional parameters: "Session ID" and "Task ID" for state management
* Validation: Proper UUID format validation and required field checks

### State-Aware Handler Implementation
* Implement a new handler for the new API version that performs state management tasks:
  * Save new state for initial requests
  * Load existing state for follow-on requests
  * Save responses and update state after processing
  * Handle authentication and user identity verification

### Persistence Abstraction
* Abstract out the persistence management to support multiple persistence providers
* Implement an in-memory persistence provider for testing and initial development
* Design interfaces to support future Redis or DynamoDB implementations
