# Phase 3 Implementation Plan: Human-in-the-Loop (HITL)

This document outlines the development tasks required to implement the Human-in-the-Loop (HITL) functionality as described in `03-02-hitl.md`, building upon the foundational architecture established in Phases 1 and 2.

## Task 1: Extend State Models for HITL

**Objective:** Update the core data models to support paused states, pending tool calls, and a new response type for HITL interventions.

- **File:** `src/sk_agents/ska_types.py`
- **Changes:**

    1.**Modify `AgentTaskItem`:** Add an optional field to store tool calls that are pending approval.
        ```python
        # In AgentTaskItem class
        pending_tool_calls: list[dict] | None = None # Store serialized FunctionCallContent
        ```
    2.**Modify `AgentTask`:** Add a "Canceled" status to the `status` literal to handle rejections.
        ```python
        # In AgentTask class
        status: Literal["Running", "Paused", "Completed", "Failed", "Canceled"]
        ```
    3.**Create `HitlResponse` Model:** Define a new Pydantic model for the response sent to the client when an intervention is required.
        ```python
        class HitlResponse(BaseModel):
            task_id: str
            session_id: str
            request_id: str
            message: str = "Human intervention required."
            approval_url: str
            rejection_url: str
            tool_calls: list[dict] # Serialized FunctionCallContent
            ```

## Task 2: Implement Persistence Layer Extension

**Objective:** Enable the retrieval of tasks using a `request_id` to support the resume endpoint.

- **Files:**
    - `src/sk_agents/persistence/task_persistence_manager.py`
    - `src/sk_agents/persistence/in_memory_persistence_manager.py`
- **Changes:**
    1. **Update `TaskPersistenceManager` ABC:** Add a new abstract method to find a task by `request_id`.
        ```python
        @abstractmethod
        def load_by_request_id(self, request_id: str) -> AgentTask | None:
            ...
        ```
    2. **Implement in `InMemoryPersistenceManager`:** Implement the new method. This will likely require creating a new index (dictionary) to map `request_id` to `task_id`. Ensure this index is properly maintained with thread-safe locks.

## Task 3: Implement HITL Trigger and Pause Logic

**Objective:** Modify the agent and handler to detect when an intervention is needed, pause the task, and persist the state.

- **Files:**
    - `src/sk_agents/hitl/hitl_manager.py`
    - `src/sk_agents/tealagents/v1alpha1/agent.py`
    - `src/sk_agents/tealagents/v1alpha1/handler.py`
- **Changes:**
    1. **Update `hitl_manager.py`:** For now, hardcode `check_for_intervention` to return `True` if a tool call's name matches a predefined "high-risk" tool (e.g., `ShellCommand`).
    2. **Create Custom Exception:** Define a custom exception, e.g., `HitlInterventionRequired(Exception)`, to signal the need for HITL from the agent to the handler.
    3. **Modify `agent.py`:** In `invoke()` and `invoke_stream()`, after extracting tool calls, iterate through them. If `check_for_intervention()` returns `True` for any of them, raise `HitlInterventionRequired` with the list of all tool calls from the LLM's response.
    4. **Modify `handler.py`:**
            - Wrap the `agent.invoke()` call in a `try...except HitlInterventionRequired` block.
            - In the `except` block:
                - Set `AgentTask.status` to `"Paused"`.
                - Create a new `AgentTaskItem` for the assistant's turn, storing the pending tool calls from the exception into the new `pending_tool_calls` field.
                - Persist the updated `AgentTask` using the `persistence_manager`.
                - Construct and return the `HitlResponse`, generating the appropriate approval and rejection URLs (e.g., `/tealagents/v1alpha1/resume/{request_id}`).

## Task 4: Create the HITL Resume Endpoint

**Objective:** Create a new API endpoint that the client can call to approve or reject a paused tool call.

- **Files:**
    - `src/sk_agents/routes.py`
    - `src/sk_agents/app.py`
    - `src/sk_agents/tealagents/v1alpha1/handler.py` (or a new `resume_handler.py`)
- **Changes:**
    1.  **Define Route in `routes.py`:** Add a new `POST` route, e.g., `/tealagents/v1alpha1/resume/{request_id}`.
    2.  **Create Resume Handler:** Implement a new handler function for this route. This function will accept the `request_id` from the URL and a simple JSON body like `{"action": "approve"}` or `{"action": "reject"}`.
    3.  **Integrate in `app.py`:** Wire the new route to the new handler function in the `AppV3` class.

## Task 5: Implement Resume and Rejection Logic

**Objective:** Implement the core logic within the resume handler to either continue execution or cancel the task.

- **File:** `src/sk_agents/tealagents/v1alpha1/handler.py` (or the new resume handler file)
- **Changes:**
    1.  **Authorization:** The request must go through the `RequestAuthorizer` to get the `user_id`.
    2.  **Load Task:** Use the new `persistence_manager.load_by_request_id()` method to fetch the `AgentTask`.
    3.  **Validation:**
        - If the task is not found, return 404.
        - Verify the `user_id` from the authorizer matches the `task.user_id`. If not, return 403 Forbidden.
        - Verify the task status is "Paused". If not, return 409 Conflict.
    4.  **Handle Rejection (`action == "reject"`):**
        - Update the `AgentTask.status` to `"Canceled"`.
        - Add an `AgentTaskItem` to the history logging the rejection.
        - Persist the task.
        - Return a confirmation response to the client.
    5.  **Handle Approval (`action == "approve"`):**
        - This is the most complex part, creating a new execution path.
        - Retrieve the `pending_tool_calls` from the last `AgentTaskItem`.
        - Execute the tool calls using `asyncio.gather()`, just as the agent would have.
        - Create `ToolContent` objects from the results.
        - Add the `AgentTaskItem` with the `pending_tool_calls` and a new `AgentTaskItem` with the `ToolContent` results to the chat history.
        - Update the `AgentTask.status` to `"Running"`.
        - Invoke the agent again with the updated chat history to get the final response from the LLM.
        - Persist the final state (`AgentTask` and new `AgentTaskItem`s).
        - Return the final `TealAgentsResponse` to the client.

## Task 6: Record Approval/Rejection

**Objective:** Ensure that the approval or rejection action is explicitly recorded in the task's history.

- **File:** `src/sk_agents/tealagents/v1alpha1/handler.py` (or the new resume handler file)
- **Changes:**
    1.  When handling an approval or rejection, create a new `AgentTaskItem` that explicitly records the action.
    2.  For approvals, this could be an item with `role: "user"` and content like `{"action": "approve", "request_id": "..."}`.
    3.  For rejections, a similar item should be added before setting the state to "Canceled".
    4.  This provides a clear audit trail within the conversation history.
