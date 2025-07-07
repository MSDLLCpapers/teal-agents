# Phase 3 - Human-in-the-Loop (HITL) Implementation Plan
## Claude Example - DO NOT USE

## Overview
This document outlines the implementation plan for Phase 3, which introduces Human-in-the-Loop (HITL) functionality to the teal-agents application. This plan assumes the baseline state described in `04-01-hitl-baseline.md` has been achieved, providing the foundation for HITL implementation.

## Prerequisites
- Phases 1 and 2 must be completed as described in `04-01-hitl-baseline.md`
- The `tealagents/v1alpha1` API must be fully functional
- Authorization, persistence, and state management infrastructure must be in place
- Tool call interception points must be established

## Implementation Tasks

### Task 1: Extend AgentTaskItem for Tool Call Persistence
**Objective**: Modify the `AgentTaskItem` model to support persistence of pending tool calls during HITL pauses.

**Files to modify**:
- `src/sk_agents/state/models.py` (or equivalent model definition file)

**Implementation details**:
1. Add optional fields to `AgentTaskItem` to store tool call information:
   - `pending_tool_calls: list[FunctionCallContent] | None` - Tool calls awaiting approval
   - `tool_call_status: Literal["pending", "approved", "rejected"] | None` - Status of tool calls
   - `approval_request_id: str | None` - Unique ID for the approval request
2. Ensure backward compatibility with existing `AgentTaskItem` instances
3. Add validation to ensure tool call fields are only populated when appropriate

**Acceptance criteria**:
- `AgentTaskItem` can store pending tool calls without breaking existing functionality
- Tool call information persists correctly through the persistence layer
- Model validation prevents invalid states

### Task 2: Create HITL Response Models
**Objective**: Create new response models for HITL approval requests, separate from existing response models.

**Files to create**:
- `src/sk_agents/tealagents/v1alpha1/models.py` (if not exists) or extend existing models file

**Implementation details**:
1. Create `HITLApprovalRequest` response model:
   - `request_id: str` - Unique identifier for the approval request
   - `task_id: str` - Task requiring approval
   - `session_id: str` - Session context
   - `user_id: str` - User who initiated the task
   - `tool_calls: list[HITLToolCallInfo]` - Tool calls requiring approval
   - `approval_url: str` - URL for approval/rejection endpoint
   - `created_at: datetime` - When the approval request was created
   - `expires_at: datetime | None` - Optional expiration time

2. Create `HITLToolCallInfo` model:
   - `function_name: str` - Name of the tool/function
   - `arguments: dict[str, Any]` - Tool arguments
   - `risk_level: str` - Risk assessment level
   - `description: str | None` - Human-readable description of the tool call

3. Create `HITLApprovalResponse` model for approval/rejection responses:
   - `request_id: str` - The request being responded to
   - `status: Literal["approved", "rejected"]` - The decision
   - `message: str | None` - Optional message about the decision
   - `processed_at: datetime` - When the decision was processed

**Acceptance criteria**:
- Models are completely separate from existing response models
- Models support all required information for HITL workflow
- Models are properly validated and serializable

### Task 3: Implement HITL Decision Persistence
**Objective**: Create a persistence layer for HITL approval/rejection decisions.

**Files to create**:
- `src/sk_agents/persistence/hitl_decisions.py`

**Implementation details**:
1. Create `HITLDecision` model:
   - `decision_id: str` - Unique identifier for the decision
   - `request_id: str` - The approval request this decision relates to
   - `user_id: str` - User who made the decision
   - `decision: Literal["approved", "rejected"]` - The decision made
   - `decided_at: datetime` - When the decision was made
   - `message: str | None` - Optional decision message

2. Create `HITLDecisionManager` abstract base class:
   - `save_decision(decision: HITLDecision) -> None`
   - `get_decision(request_id: str) -> HITLDecision | None`
   - `get_decisions_for_user(user_id: str) -> list[HITLDecision]`

3. Create `InMemoryHITLDecisionManager` implementation:
   - Thread-safe in-memory storage
   - Follows same patterns as existing persistence managers

4. Create `HITLDecisionFactory` for pluggable decision persistence:
   - Environment variables: `TA_HITL_DECISION_MODULE`, `TA_HITL_DECISION_CLASS`
   - Default to in-memory implementation

**Acceptance criteria**:
- HITL decisions are persisted reliably
- Decision persistence follows established patterns
- Factory pattern allows pluggable implementations

### Task 4: Enhance HITL Manager with Risk Assessment
**Objective**: Implement the core HITL logic in the existing `hitl_manager.py` placeholder.

**Files to modify**:
- `src/sk_agents/hitl/hitl_manager.py`

**Implementation details**:
1. Replace placeholder `check_for_intervention()` with full implementation:
   - Accept `FunctionCallContent` parameter
   - Implement risk assessment logic (placeholder for now)
   - Return `bool` indicating if intervention is required

2. Add `create_approval_request()` method:
   - Accept list of `FunctionCallContent` objects
   - Generate unique `request_id`
   - Create `HITLApprovalRequest` model
   - Generate approval URL with `request_id`

3. Add configuration for risk assessment:
   - Environment variables for risk levels
   - Configurable high-risk tool patterns/names

4. Add logging and telemetry for HITL events:
   - Tool call interceptions
   - Approval request creations
   - Decision processing

**Acceptance criteria**:
- Risk assessment logic is configurable and extensible
- Approval requests are created with all required information
- HITL events are properly logged for monitoring

### Task 5: Implement Resume Endpoint
**Objective**: Create the resume endpoint that handles approval/rejection of tool calls.

**Files to create**:
- `src/sk_agents/tealagents/v1alpha1/resume_handler.py`

**Files to modify**:
- `src/sk_agents/routes.py` (add new endpoint)
- `src/sk_agents/tealagents/v1alpha1/handler.py` (add resume logic)

**Implementation details**:
1. Create `HITLResumeHandler` class:
   - `handle_resume(request_id: str, action: Literal["approve", "reject"], auth_header: str) -> HITLApprovalResponse`
   - Validate user authorization matches original task user
   - Load task and verify it's in paused state
   - Save approval/rejection decision
   - Update task status and continue processing (for approvals)

2. Add `/tealagents/v1alpha1/resume/{request_id}` endpoint:
   - POST method with `{"action": "approve" | "reject", "message": str | None}`
   - Authorization header required
   - Return `HITLApprovalResponse`

3. Implement resume logic:
   - For approvals: Continue agent execution from paused state
   - For rejections: Mark task as cancelled/failed
   - Update task status appropriately

4. Add error handling:
   - Invalid request IDs
   - Unauthorized access
   - Already processed requests
   - Task state validation

**Acceptance criteria**:
- Resume endpoint properly validates authorization
- Approved tasks continue execution seamlessly
- Rejected tasks are properly cancelled
- All edge cases are handled with appropriate error responses

### Task 6: Modify Agent to Support HITL Workflow
**Objective**: Update the agent implementation to handle HITL pausing and resuming.

**Files to modify**:
- `src/sk_agents/tealagents/v1alpha1/agent.py`

**Implementation details**:
1. Modify tool call processing loop:
   - Check each tool call with `hitl_manager.check_for_intervention()`
   - If intervention required, create approval request and pause task
   - Return `HITLApprovalRequest` instead of continuing execution

2. Add `resume_from_approval()` method:
   - Accept approved tool calls and continue execution
   - Restore conversation state from persistence
   - Execute approved tools and continue normal flow

3. Update both `invoke()` and `invoke_stream()` methods:
   - Handle HITL pausing in both sync and streaming modes
   - Ensure consistent behavior between modes

4. Add task state management:
   - Set task status to "Paused" when HITL required
   - Update task with pending tool calls
   - Restore task status when resuming

**Acceptance criteria**:
- Agent correctly identifies high-risk tool calls
- Task state is properly managed during pausing/resuming
- Both sync and streaming modes support HITL workflow
- Conversation continuity is maintained across pause/resume cycles

### Task 7: Update Handler for HITL Integration
**Objective**: Modify the main handler to support HITL responses and workflow.

**Files to modify**:
- `src/sk_agents/tealagents/v1alpha1/handler.py`

**Implementation details**:
1. Update response handling:
   - Support returning `HITLApprovalRequest` responses
   - Maintain existing response types for non-HITL scenarios
   - Ensure proper content-type headers for different response types

2. Add HITL-specific error handling:
   - Handle approval request creation failures
   - Manage task state inconsistencies
   - Provide meaningful error messages for HITL-related failures

3. Update streaming support:
   - Handle HITL pauses in streaming responses
   - Ensure proper connection management when pausing

4. Add telemetry for HITL events:
   - Track approval request creation
   - Monitor resume success/failure rates
   - Log HITL-related performance metrics

**Acceptance criteria**:
- Handler properly routes HITL responses
- Streaming behavior is consistent with sync behavior
- Error handling provides clear diagnostics
- Telemetry supports monitoring HITL performance

### Task 8: Add HITL Configuration and Environment Variables
**Objective**: Add configuration options for HITL functionality.

**Files to modify**:
- `src/sk_agents/configs.py` (or equivalent configuration file)

**Implementation details**:
1. Add HITL-specific environment variables:
   - `TA_HITL_DECISION_MODULE` - Module for HITL decision persistence
   - `TA_HITL_DECISION_CLASS` - Class for HITL decision persistence
   - `TA_HITL_RISK_ASSESSMENT_MODULE` - Module for risk assessment logic
   - `TA_HITL_RISK_ASSESSMENT_CLASS` - Class for risk assessment logic
   - `TA_HITL_APPROVAL_TIMEOUT` - Timeout for approval requests
   - `TA_HITL_BASE_URL` - Base URL for generating approval URLs

2. Add configuration validation:
   - Ensure required HITL components are properly configured
   - Validate URL formats and timeouts
   - Provide sensible defaults for development

3. Add configuration documentation:
   - Document all HITL-related environment variables
   - Provide example configurations
   - Include troubleshooting guidance

**Acceptance criteria**:
- All HITL functionality is properly configurable
- Configuration validation prevents misconfigurations
- Documentation supports easy setup and troubleshooting

### Task 9: Implement HITL Integration Tests
**Objective**: Create comprehensive tests for HITL functionality.

**Files to create**:
- `tests/test_hitl_manager.py`
- `tests/test_hitl_resume_handler.py`
- `tests/test_hitl_integration.py`

**Implementation details**:
1. Test HITL manager functionality:
   - Risk assessment logic
   - Approval request creation
   - Configuration handling

2. Test resume handler:
   - Authorization validation
   - Approval/rejection processing
   - Error handling scenarios

3. Test end-to-end HITL workflow:
   - Complete approval workflow
   - Complete rejection workflow
   - Concurrent request handling
   - Task state management

4. Test edge cases:
   - Expired approval requests
   - Duplicate approvals
   - Invalid request IDs
   - Authorization failures

**Acceptance criteria**:
- All HITL functionality is thoroughly tested
- Edge cases are properly handled
- Integration tests validate end-to-end workflows
- Test coverage meets project standards

### Task 10: Update Documentation and Examples
**Objective**: Document HITL functionality and provide usage examples.

**Files to create**:
- `doc/hitl-workflow.md`
- `demos/11_hitl_approval/` (example directory)

**Files to modify**:
- `README.md` (add HITL overview)

**Implementation details**:
1. Create comprehensive HITL documentation:
   - Workflow overview and diagrams
   - Configuration guide
   - API reference for resume endpoint
   - Troubleshooting guide

2. Create example implementation:
   - Sample configuration for HITL
   - Example client code for handling approval requests
   - Demo of high-risk tool requiring approval

3. Update main documentation:
   - Add HITL to feature overview
   - Include in getting started guide
   - Update API documentation

**Acceptance criteria**:
- Documentation clearly explains HITL workflow
- Examples demonstrate practical usage
- Integration with existing documentation is seamless

## Implementation Dependencies

### Task Dependencies
1. **Task 1** (Extend AgentTaskItem) - No dependencies, foundational
2. **Task 2** (HITL Response Models) - No dependencies, foundational
3. **Task 3** (HITL Decision Persistence) - No dependencies, foundational
4. **Task 4** (Enhance HITL Manager) - Depends on Tasks 1, 2, 3
5. **Task 5** (Resume Endpoint) - Depends on Tasks 2, 3, 4
6. **Task 6** (Modify Agent) - Depends on Tasks 1, 4
7. **Task 7** (Update Handler) - Depends on Tasks 2, 5, 6
8. **Task 8** (Configuration) - Depends on Tasks 3, 4
9. **Task 9** (Integration Tests) - Depends on Tasks 1-8
10. **Task 10** (Documentation) - Depends on Tasks 1-9

### Recommended Implementation Order
1. **Phase 1**: Tasks 1, 2, 3 (Foundation models and persistence)
2. **Phase 2**: Tasks 4, 8 (Core HITL logic and configuration)
3. **Phase 3**: Tasks 5, 6, 7 (Integration with existing systems)
4. **Phase 4**: Tasks 9, 10 (Testing and documentation)

## Risk Assessment and Mitigation

### Technical Risks
1. **State Management Complexity**: Managing paused tasks and conversation state
   - *Mitigation*: Comprehensive testing of state transitions
   - *Validation*: Integration tests covering all state scenarios

2. **Concurrent Request Handling**: Multiple approval requests for same user
   - *Mitigation*: Proper locking in persistence layer
   - *Validation*: Concurrent access testing

3. **Streaming Response Handling**: Pausing streaming responses for HITL
   - *Mitigation*: Careful connection management and timeout handling
   - *Validation*: Streaming-specific test scenarios

### Operational Risks
1. **Approval Request Expiration**: Handling expired approval requests
   - *Mitigation*: Configurable timeouts and cleanup processes
   - *Validation*: Monitoring and alerting for expired requests

2. **Authorization Validation**: Ensuring only authorized users can approve
   - *Mitigation*: Rigorous authorization checking and audit logging
   - *Validation*: Security testing of authorization flows

## Success Criteria

### Functional Requirements
- [ ] High-risk tool calls trigger HITL approval requests
- [ ] Users can approve/reject tool calls via resume endpoint
- [ ] Approved tool calls continue execution seamlessly
- [ ] Rejected tool calls result in cancelled tasks
- [ ] All HITL decisions are persisted and auditable

### Non-Functional Requirements
- [ ] HITL workflow adds minimal latency to non-HITL requests
- [ ] System maintains existing performance characteristics
- [ ] HITL functionality is fully configurable and pluggable
- [ ] Error handling provides clear diagnostics for HITL issues

### Security Requirements
- [ ] Authorization is validated for all HITL operations
- [ ] HITL decisions are properly attributed to users
- [ ] Approval URLs are secure and cannot be guessed
- [ ] No sensitive information is exposed in HITL responses

## Future Considerations

### Extensibility Points
1. **Risk Assessment Logic**: Pluggable risk assessment modules
2. **Approval Workflows**: Support for multi-step approval processes
3. **Notification Systems**: Integration with external notification services
4. **Audit and Compliance**: Enhanced logging and audit trails

### Integration Opportunities
1. **Authentication Integration**: Support for OAuth/OIDC approval flows
2. **Consent Management**: Integration with consent management platforms
3. **Monitoring Integration**: Enhanced telemetry for HITL operations
4. **Client SDKs**: Language-specific SDKs for handling HITL workflows

## Summary

This implementation plan provides a comprehensive approach to adding Human-in-the-Loop functionality to the teal-agents application. The plan is structured to build upon the existing baseline infrastructure while maintaining backward compatibility and system reliability.

The phased approach ensures that foundational components are established first, followed by integration with existing systems, and finally comprehensive testing and documentation. Each task includes specific acceptance criteria and implementation details to guide development.

The resulting HITL implementation will provide a flexible, secure, and extensible foundation for requiring human approval of high-risk tool calls while maintaining the performance and reliability of the existing system.
