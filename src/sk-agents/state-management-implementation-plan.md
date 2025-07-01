# State Management Implementation Plan for Teal Agents

This document outlines the comprehensive implementation plan for integrating state management into the Teal Agents platform. The plan is organized into epics, stories, and tasks to provide a clear roadmap for development.

## Epic 1: State Management Infrastructure

This epic covers the foundational architecture and infrastructure needed to support stateful agent invocations.

### Story 1.1: Define State Management Interfaces and Data Models

**Description:** Create the necessary interfaces and data models to standardize state management across the application.

**Tasks:**
- [ ] Define `StateManager` interface with core methods (save, load, update, delete)
- [ ] Create comprehensive data models for `Session`, `Task`, and `Request` entities:
  - **Session Model**: session_id, user_id, created_at, last_updated_at, metadata
  - **Task Model**: task_id, session_id, user_id, status, interaction_history, execution_trace, created_at, last_updated_at, metadata
  - **Request Model**: request_id, task_id, status, created_at, completed_at, metadata
- [ ] Define state status enums (Running, Paused, Completed, Failed)
- [ ] Implement serialization/deserialization mechanisms for state objects
- [ ] Add proper indexing and relationships between entities
- [ ] Include "last_updated_at" timestamps for future cleanup capabilities
- [ ] Design for concurrent access safety

**Acceptance Criteria:**
- Interfaces and data models are well-documented with clear responsibilities
- Models include all necessary metadata (timestamps, user IDs, etc.)
- Concurrent access patterns are safely handled
- Unit tests validate the behavior of serialization/deserialization

### Story 1.2: Implement In-Memory State Provider

**Description:** Create an in-memory implementation of the state management interface for development and testing.

**Tasks:**
- [ ] Implement `InMemoryStateManager` class
- [ ] Add thread-safe access mechanisms using proper locking
- [ ] Handle concurrent access to the same task safely
- [ ] Create unit tests covering all state operations including concurrency scenarios
- [ ] Add configuration options for memory limits
- [ ] Implement proper cleanup of memory usage

**Acceptance Criteria:**
- In-memory provider passes all unit tests including concurrency tests
- Provider correctly handles concurrent operations without data corruption
- Memory usage is monitored and controlled
- No automatic cleanup is implemented (preserve all task data)

### Story 1.3: Create State Provider Factory

**Description:** Implement a factory pattern to select and instantiate the appropriate state provider based on configuration.

**Tasks:**
- [ ] Create `StateManagerFactory` class
- [ ] Implement provider registration mechanism
- [ ] Add configuration options for provider selection
- [ ] Implement lazy initialization pattern
- [ ] Design interfaces for future Redis or DynamoDB implementations
- [ ] Create unit tests for factory logic

**Acceptance Criteria:**
- Factory correctly initializes the configured provider
- Error handling for misconfiguration is robust
- Documentation clearly explains configuration options
- Future provider implementations can be easily added

## Epic 2: New API Version Implementation (tealagents/v1alpha1)

This epic covers the creation of a completely isolated `tealagents/v1alpha1` API version with state management capabilities.

### Story 2.1: Create Isolated Module Structure for New API

**Description:** Establish a completely separate module structure for the new API version to maintain 100% backward compatibility.

**Tasks:**
- [ ] Create new top-level module directory `tealagents` parallel to `skagents`
- [ ] Create `v1alpha1` subdirectory within `tealagents`
- [ ] Implement separate `__init__.py` with dedicated handler factory
- [ ] Create module structure following existing patterns:
  ```
  tealagents/
    __init__.py           # Handler factory for tealagents API versions
    v1alpha1/             # Specific version implementation
      __init__.py         # Entry point for this API version
      handler.py          # State-aware handler implementation
      models.py           # Data models including UserMessage
      routes.py           # Route definitions (if needed)
      state/              # State management implementation
  ```
- [ ] Ensure complete isolation from existing `skagents` modules

**Acceptance Criteria:**
- New API version has completely separate code path from existing versions
- No shared code that could impact existing functionality
- Module structure follows the same patterns as existing modules
- Unit tests confirm isolation of the new API version

### Story 2.2: Implement UserMessage Data Model

**Description:** Create a comprehensive `UserMessage` data model that represents a single multi-modal message for the stateful API.

**Tasks:**
- [ ] Create `UserMessage` class that does NOT inherit from `BaseMultiModalInput`
- [ ] Structure the model with the following fields:
  - `session_id`: Optional[str] - Identifier for the conversation session
  - `task_id`: Optional[str] - Identifier for the specific task
  - `items`: List[MultiModalItem] - List of content items (text, images, etc.)
- [ ] Remove `chat_history` field since history is managed server-side
- [ ] Implement validation logic for UUID format verification
- [ ] Add proper field validation and error messages
- [ ] Create helper methods for common operations
- [ ] Implement comprehensive unit tests

**Example Structure:**
```python
class UserMessage(BaseModel):
    session_id: Optional[str] = Field(None, description="Session identifier")
    task_id: Optional[str] = Field(None, description="Task identifier") 
    items: List[MultiModalItem] = Field(..., description="Message content items")
    
    @validator('session_id', 'task_id')
    def validate_uuid_format(cls, v):
        # UUID validation logic
```

**Acceptance Criteria:**
- `UserMessage` correctly represents a single multi-modal message
- Does not inherit from `BaseMultiModalInput` but has similar structure
- UUID validation works properly for session_id and task_id
- Documentation clearly explains each field's purpose
- Unit tests cover all validation scenarios

### Story 2.3: Implement Authentication Integration

**Description:** Create authentication middleware and user identity extraction for the new API version.

**Tasks:**
- [ ] Create `AuthenticationMiddleware` for token validation
- [ ] Implement mock user identity extraction for initial development
- [ ] Add user identity storage with task state
- [ ] Implement user ownership verification for task access
- [ ] Return 401 errors for unauthorized access attempts
- [ ] Plan follow-up tasks for actual Entra ID integration
- [ ] Create comprehensive unit tests with mocked authentication

**Acceptance Criteria:**
- Authentication middleware properly extracts user identity
- User ownership is verified for task access
- Unauthorized access is properly rejected with 401
- Mock implementation allows for development without Entra ID setup
- Documentation explains integration points for real authentication

### Story 2.4: Implement State-Aware Handler

**Description:** Create a dedicated handler for the new API version that fully integrates state management.

**Tasks:**
- [ ] Create `TealAgentsV1Alpha1Handler` class implementing `BaseHandler`
- [ ] Implement logic for initial requests (no task_id provided):
  - Generate new session_id if not provided
  - Create new task_id and request_id
  - Save initial state
- [ ] Implement logic for follow-on requests (task_id provided):
  - Validate user ownership of task
  - Load existing state
  - Generate new request_id
- [ ] Build chat history from stored state
- [ ] Save responses and update state after processing
- [ ] Handle all error scenarios with appropriate 5xx responses
- [ ] Implement comprehensive unit tests

**Acceptance Criteria:**
- Handler correctly processes both initial and follow-on requests
- State is properly created, loaded, and persisted
- Authentication and authorization checks are enforced
- Error handling provides appropriate response codes
- Unit tests cover all logical branches

### Story 2.5: Create Response Models with State Information

**Description:** Implement comprehensive response models that include all necessary state information.

**Tasks:**
- [ ] Create `TealAgentsResponse` class with state identifiers:
  - `content`: str - The response content
  - `session_id`: str - Session identifier
  - `task_id`: str - Task identifier
  - `request_id`: str - Request identifier
  - `status`: TaskStatus - Current task status
  - `metadata`: Optional[Dict] - Additional metadata
  - `created_at`: datetime - Response timestamp
- [ ] Implement proper serialization for all data types
- [ ] Add validation for all fields
- [ ] Create unit tests for response models

**Acceptance Criteria:**
- Response models include all required state identifiers
- Serialization correctly handles all data types
- Validation ensures data integrity
- Unit tests cover all scenarios

### Story 2.6: Implement Route Integration Strategy

**Description:** Determine and implement the optimal route integration approach for the new API version.

**Tasks:**
- [ ] Analyze feasibility of reusing existing `routes.py` `get_rest_routes` function
- [ ] If reusable: Configure existing routes with new parameters for tealagents logic
- [ ] If not reusable: Create new route handling logic that maintains existing capabilities:
  - Preserve telemetry functionality
  - Implement proper error handling
  - Support both REST and SSE endpoints
- [ ] Exclude websocket routes (`get_websocket_routes`) as they are deprecated
- [ ] Create `AppV3` class following same pattern as `AppV1` and `AppV2`
- [ ] Update main `app.py` to detect `tealagents/v1alpha1` and route to `AppV3`

**Acceptance Criteria:**
- Route integration maintains all existing telemetry capabilities
- New API version is properly detected and routed
- No impact on existing API versions
- Both REST and SSE endpoints work correctly

### Story 2.7: Implement SSE Streaming Support

**Description:** Create comprehensive SSE streaming support for the stateful API with proper state management.

**Tasks:**
- [ ] Implement state-aware SSE streaming endpoint
- [ ] Update state during streaming operations
- [ ] Add state identifiers to each streamed event
- [ ] Implement keepalive mechanisms for long-running operations (30-second dummy events)
- [ ] Handle streaming errors and state recovery
- [ ] Create integration tests for streaming functionality

**Acceptance Criteria:**
- Streaming responses include state identifiers in each event
- State is properly updated during streaming
- Keepalive events prevent timeouts during long LLM calls
- Error handling and recovery work correctly
- Streaming performance meets requirements

## Epic 3: Configuration and Integration

This epic covers configuration management and integration with the existing application structure.

### Story 3.1: Implement Configuration Detection and Validation

**Description:** Ensure the new API version integrates properly with the existing configuration system.

**Tasks:**
- [ ] Add detection for `apiVersion: tealagents/v1alpha1` in configuration files
- [ ] Maintain existing configuration file structure (reference: `demos/ZZ_wikipedia_demo/config.yaml`)
- [ ] Ensure 100% backward compatibility with existing API versions:
  - `skagents/v1` (example: `demos/03_plugins/config.yaml`)
  - `skagents/v2alpha1` (example: `demos/10_chat_plugins/config.yaml`)
- [ ] Create configuration validation for the new API version
- [ ] Add unit tests for configuration detection

**Acceptance Criteria:**
- New API version is properly detected from configuration
- Existing API versions continue to work unchanged
- Configuration validation provides clear error messages
- Documentation explains configuration options

### Story 3.2: Update Main Application Integration

**Description:** Integrate the new API version into the main application flow.

**Tasks:**
- [ ] Update `app.py` to detect `tealagents/v1alpha1` API version
- [ ] Create `AppV3` class following existing patterns
- [ ] Ensure complete isolation from existing `AppV1` and `AppV2` functionality
- [ ] Implement proper error handling for unsupported configurations
- [ ] Create integration tests for the complete flow

**Acceptance Criteria:**
- Main application correctly routes to new API version
- Existing functionality remains completely unchanged
- Error handling is comprehensive and informative
- Integration tests validate end-to-end functionality

## Epic 4: Testing and Documentation

This epic ensures comprehensive testing and documentation for the new state management capabilities.

### Story 4.1: Create Comprehensive Test Suite

**Description:** Develop a thorough test suite covering all aspects of state management.

**Tasks:**
- [ ] Create unit tests for all state management components
- [ ] Implement integration tests for complete state flow scenarios
- [ ] Add concurrency tests for state access safety
- [ ] Create error scenario tests (persistence failures, corrupted state)
- [ ] Implement performance tests for state operations
- [ ] Add security tests for authentication and authorization
- [ ] Ensure test coverage exceeds 80% for new code

**Acceptance Criteria:**
- Comprehensive test coverage for all new functionality
- Concurrency safety is thoroughly tested
- Error scenarios are properly validated
- Performance benchmarks are established
- Security measures are validated

### Story 4.2: Create Developer Documentation

**Description:** Create comprehensive documentation for developers using the stateful API.

**Tasks:**
- [ ] Create API reference documentation for `tealagents/v1alpha1`
- [ ] Write developer guides for stateful interactions
- [ ] Document the UserMessage model and response formats
- [ ] Create examples demonstrating state management flows
- [ ] Add troubleshooting guides for common issues
- [ ] Document configuration options and authentication requirements

**Acceptance Criteria:**
- Documentation is clear, comprehensive, and actionable
- Examples cover common use cases and edge cases
- API reference is complete and accurate
- Troubleshooting guides address likely issues

### Story 4.3: Create Migration and Integration Guides

**Description:** Help existing clients understand and adopt the new stateful API.

**Tasks:**
- [ ] Document differences between stateless and stateful APIs
- [ ] Create step-by-step migration guide from existing versions
- [ ] Add before/after code examples
- [ ] Document performance and operational considerations
- [ ] Create client SDK or integration helpers
- [ ] Add operational documentation for deployment and monitoring

**Acceptance Criteria:**
- Migration guide is clear and actionable
- Examples demonstrate practical migration scenarios
- Operational considerations are well-documented
- Integration helpers simplify adoption

## Implementation Timeline

### Phase 1: Foundation (Weeks 1-2)
- Epic 1: State Management Infrastructure
- Story 2.1: Create Isolated Module Structure

### Phase 2: Core Implementation (Weeks 3-4)
- Story 2.2: Implement UserMessage Data Model
- Story 2.3: Implement Authentication Integration
- Story 2.4: Implement State-Aware Handler
- Story 2.5: Create Response Models

### Phase 3: Integration and Routes (Weeks 5-6)
- Story 2.6: Implement Route Integration Strategy
- Story 2.7: Implement SSE Streaming Support
- Epic 3: Configuration and Integration

### Phase 4: Testing and Documentation (Weeks 7-8)
- Epic 4: Testing and Documentation
- Final integration testing and validation

## Key Design Principles

### Complete Isolation
- The new `tealagents/v1alpha1` API version must be completely isolated from existing versions
- No shared code that could impact existing functionality
- 100% backward compatibility maintained

### Authentication-First Design
- Authentication and user identity are central to the state management approach
- Mock implementations allow development without immediate Entra ID setup
- User ownership verification is enforced for all task operations

### Flexible State Management
- Abstract state management allows multiple provider implementations
- In-memory implementation sufficient for initial development
- Designed for future Redis or DynamoDB implementations

### Error Handling Strategy
- Persistence failures result in 5xx response codes
- Comprehensive error messages for debugging
- Proper timeout handling for long-running operations
- Keepalive mechanisms for SSE streams

### Concurrency Safety
- Thread-safe access to shared state
- Proper handling of concurrent task access
- Data corruption prevention mechanisms

## Risk Mitigation

### Performance Risks
- State management adds overhead to request processing
- Mitigation: Abstract design allows optimization of provider implementations
- Monitoring and benchmarking included in testing strategy

### Security Risks
- State data may contain sensitive information
- Mitigation: Authentication-first design with user ownership verification
- Comprehensive security testing included

### Compatibility Risks
- New functionality might impact existing systems
- Mitigation: Complete isolation and comprehensive testing
- 100% backward compatibility maintained

### Operational Risks
- State persistence introduces new operational complexity
- Mitigation: Start with in-memory implementation
- Comprehensive documentation for operations teams
