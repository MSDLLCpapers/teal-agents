# Refined State Management Implementation Plan

This plan is based on the practical implementation approach outlined in `my-list.md` with necessary additions for completeness.

## Phase 1: Core Infrastructure (Week 1)

### 1. Authorization Infrastructure
**Files to create:**
- `src/sk_agents/authorization/request_authorizer.py` - Abstract base class
- `src/sk_agents/authorization/dummy_authorizer.py` - Mock implementation
- `src/sk_agents/authorization/authorizer_factory.py` - Factory implementation

**Tasks:**
- [ ] Create abstract `RequestAuthorizer` class:
  ```python
  @abstractmethod
  def authorize_request(self, auth_header: str) -> str:
      """Returns authorized unique user identifier"""
      pass
  ```
- [ ] Implement `DummyAuthorizer` that always returns 'dummyuser'
- [ ] Create `AuthorizerFactory` with environment variable configuration:
  - `TEAL_AUTHORIZER_MODULE` - Module path for authorizer implementation
  - `TEAL_AUTHORIZER_CLASS` - Class name for authorizer implementation
- [ ] Add thread-safe singleton pattern to factory for performance
- [ ] Include comprehensive error handling for import failures and misconfigurations

### 2. Persistence Infrastructure
**Files to create:**
- `src/sk_agents/persistence/task_persistence_manager.py` - Abstract base class
- `src/sk_agents/persistence/in_memory_persistence_manager.py` - In-memory implementation
- `src/sk_agents/persistence/persistence_factory.py` - Factory implementation

**Tasks:**
- [ ] Create abstract `TaskPersistenceManager` class with methods:
  - `create(task: AgentTask) -> None`
  - `load(task_id: str) -> AgentTask | None`
  - `update(task: AgentTask) -> None`
  - `delete(task_id: str) -> None`
- [ ] Implement `InMemoryPersistenceManager` with thread-safe concurrent access using proper locking mechanisms
- [ ] Create `PersistenceFactory` with environment variable configuration:
  - `TEAL_PERSISTENCE_MODULE` - Module path for persistence implementation
  - `TEAL_PERSISTENCE_CLASS` - Class name for persistence implementation
- [ ] Add proper error handling for persistence failures (should result in 5xx responses)
- [ ] Include memory management and monitoring for in-memory implementation

### 3. Data Models
**Files to create:**
- `src/sk_agents/tealagents/models.py` - All data models for tealagents

**Tasks:**
- [ ] Create `UserMessage` model (does NOT inherit from `BaseMultiModalInput`):
  ```python
  class UserMessage(BaseModel):
      session_id: str | None = None
      task_id: str | None = None
      items: list[MultiModalItem]
  ```
- [ ] Create `AgentTaskItem` model:
  ```python
  class AgentTaskItem(BaseModel):
      task_id: str
      role: Literal["user", "assistant"]
      item: MultiModalItem
      request_id: str
      updated: datetime
  ```
- [ ] Create `AgentTask` model:
  ```python
  class AgentTask(BaseModel):
      task_id: str
      session_id: str
      user_id: str  # Added based on feedback
      items: list[AgentTaskItem]
      created_at: datetime
      last_updated_at: datetime
      status: Literal["Running", "Paused", "Completed", "Failed"] = "Running"
  ```
- [ ] Create new response models that collapse `output_raw` and `output_pydantic` to single `output` field:
  ```python
  class TealAgentsResponse(BaseModel):
      session_id: str
      task_id: str
      request_id: str
      output: str  # Collapsed from output_raw/output_pydantic
      # ... all other existing InvokeResponse fields remain
      
  class TealAgentsPartialResponse(BaseModel):
      session_id: str
      task_id: str
      request_id: str
      output_partial: str
      # ... all other existing PartialResponse fields remain
  ```

## Phase 2: New API Version Structure (Week 2)

### 4. Module Structure
**Directories to create:**
- `src/sk_agents/tealagents/`
- `src/sk_agents/tealagents/v1alpha1/`

**Files to create:**
- `src/sk_agents/tealagents/__init__.py` - Top-level handler factory
- `src/sk_agents/tealagents/v1alpha1/__init__.py` - Version-specific entry point
- `src/sk_agents/tealagents/v1alpha1/agent.py` - State-aware BaseHandler implementation

**Specific isolation requirements:**
- [ ] No imports from `skagents` modules in `tealagents` modules
- [ ] No shared mutable state between API versions
- [ ] Separate error handling paths to prevent cross-contamination
- [ ] Independent configuration validation logic
- [ ] Unit tests to verify complete isolation (test that changes to tealagents don't affect skagents behavior)

### 5. Handler Implementation
**File:** `src/sk_agents/tealagents/v1alpha1/agent.py`

**Tasks:**
- [ ] Create `TealAgentsV1Alpha1Handler` class implementing `BaseHandler`
- [ ] Implement `invoke` method with complete state management flow:
  - Authorize request using factory-provided authorizer
  - Generate session_id if not provided
  - Generate request_id for this invocation
  - Handle task_id logic (load existing vs create new)
  - Verify user ownership for existing tasks (return 401 if mismatch)
  - Build chat history from stored AgentTaskItem objects
  - Invoke LLM and save response
  - Return TealAgentsResponse with all state identifiers
- [ ] Implement `invoke_stream` method with state management:
  - Same authorization and state loading logic as invoke
  - Stream TealAgentsPartialResponse objects with state identifiers
  - Save final response to task state
  - Include keepalive mechanisms for long-running operations (30-second dummy events)
- [ ] Add comprehensive error handling with appropriate HTTP status codes

## Phase 3: Application Integration (Week 3)

### 6. Route Integration
**Files to modify:**
- `src/sk_agents/routes.py` - Minor updates to support tealagents routing
- `src/sk_agents/appv3.py` - New application class

**Tasks:**
- [ ] Update `routes.py` to route to tealagents handlers when `tealagents` is detected as first token in apiVersion
- [ ] Preserve all existing telemetry functionality in route updates
- [ ] Create `AppV3` class following same pattern as `AppV1` and `AppV2`:
  - Extract configuration information
  - Set up routes using updated `routes.py` functionality
  - Initialize any tealagents-specific middleware or configuration

### 7. Main Application Updates
**Files to modify:**
- `src/sk_agents/app.py` - Add AppV3 routing logic

**Tasks:**
- [ ] Update main application to detect `tealagents/v1alpha1` apiVersion in configuration:
  - Split apiVersion on `/` and check if first token is `tealagents`
  - Route to `AppV3` when tealagents API version is detected
  - Maintain complete backward compatibility with existing routing logic
- [ ] Ensure configuration file structure remains identical (reference: `demos/ZZ_wikipedia_demo/config.yaml`)
- [ ] Add proper error handling for unsupported tealagents versions

## Phase 4: Testing and Validation (Week 4)

### 8. Comprehensive Testing
**Test files to create:**
- `tests/test_tealagents_handler.py`
- `tests/test_authorization.py`
- `tests/test_persistence.py`
- `tests/test_isolation.py`

**Test scenarios:**
- [ ] Unit tests for all new components with >80% coverage
- [ ] Concurrency tests for thread-safe state access (multiple simultaneous requests to same task)
- [ ] Authorization tests (valid user, invalid user, missing auth header)
- [ ] Persistence failure scenarios (should return 5xx responses)
- [ ] State corruption scenarios (should return 5xx responses)
- [ ] Complete isolation tests (verify tealagents changes don't affect skagents)
- [ ] End-to-end integration tests for complete state flow scenarios
- [ ] SSE streaming tests with state management
- [ ] Performance benchmarks for state operations

### 9. Configuration and Error Handling
**Tasks:**
- [ ] Validate that existing API versions continue to work unchanged:
  - `skagents/v1` (test with `demos/03_plugins/config.yaml`)
  - `skagents/v2alpha1` (test with `demos/10_chat_plugins/config.yaml`)
- [ ] Test new API version with `tealagents/v1alpha1` configuration
- [ ] Verify proper error messages for:
  - Invalid authorization
  - Persistence failures
  - Task not found
  - User ownership mismatches
  - Configuration errors
- [ ] Test timeout handling for long-running operations

## Implementation Notes

### Concurrency Safety
- Use proper locking mechanisms in `InMemoryPersistenceManager`
- Handle race conditions for concurrent access to same task
- Ensure thread-safe access to shared state throughout the application

### Error Handling Strategy
- Persistence failures → 5xx responses
- Authorization failures → 401 responses
- Task ownership violations → 401 responses
- Configuration errors → 500 responses with clear messages
- Invalid task_id → 404 responses

### SSE Streaming Considerations
- Include state identifiers (session_id, task_id, request_id) in each streamed event
- Update task state during streaming operations
- Implement keepalive events for long LLM calls (30-second intervals)
- Handle streaming errors and state recovery gracefully

### Performance Considerations
- Lazy initialization of factories to minimize startup overhead
- Efficient chat history reconstruction from AgentTaskItem objects
- Monitor memory usage in InMemoryPersistenceManager
- Consider connection pooling for future persistent storage implementations

### Future Extensibility
- Abstract interfaces support future Redis/DynamoDB implementations
- Authorization abstraction allows for real Entra ID integration
- State models include timestamps for future cleanup implementations
- Response models designed to support future HITL requirements

## Environment Variables

New environment variables introduced:
- `TEAL_AUTHORIZER_MODULE` - Module path for authorization implementation
- `TEAL_AUTHORIZER_CLASS` - Class name for authorization implementation
- `TEAL_PERSISTENCE_MODULE` - Module path for persistence implementation
- `TEAL_PERSISTENCE_CLASS` - Class name for persistence implementation

Default values for development:
- Authorizer: `sk_agents.authorization.dummy_authorizer.DummyAuthorizer`
- Persistence: `sk_agents.persistence.in_memory_persistence_manager.InMemoryPersistenceManager`
