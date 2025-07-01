# State Management for Distributed Agentic Systems

This document outlines the state management model for a complex, multi-agent, and multi-orchestrator system. This model is designed to support advanced features like long-running, stateful tasks and Human-in-the-Loop (HITL) interventions.

## Core Concepts

The architecture is built on three fundamental state primitives: **Sessions**, **Tasks**, and **Requests**. This separation provides the necessary granularity to manage complex, asynchronous workflows in a reliable and auditable manner.

```mermaid
sequenceDiagram
    participant C as Client
    participant O1 as Orchestrator 1
    participant A1 as Agent 1
    participant A2 as Agent 2
    participant O2 as Orchestrator 2
    participant A3 as Agent 3
    participant A4 as Agent 4
    participant RH as Resume Handler

    C->>O1: Initial Invocation
    O1->>O1: Generate Session ID, Task ID, Request ID (S1/T1/R1)
    O1->>A1: Subtask 1 Invocation with Session ID S1
    A1->>A1: Generate Task ID, Request ID (T2/R2)
    O1->>A2: Subtask 2 Invocation with Session ID S1
    A2->>A2: Generate Task ID, Request ID (T3/R3)
    O1->>O2: Subtask 3 Invocation with Session ID S1
    O2->>O2: Generate Task ID, Request ID (T4/R4)
    O2->>A3: Subtask 4 Invocation with Session ID S1
    A3->>A3: Generate Task ID, Request ID (T5/R5)
    O2->>A4: Subtask 5 Invocation with Session ID S1
    A4->>A4: Generate Task ID, Request ID (T6/R6)
    A1-->>O1: Subtask 1 Response (T2/R2)
    A2-->>O1: Subtask 2 Response (T3/R3)
    A3-->>O2: Subtask 4 Response (T5/R5)
    A4-->>O2: Subtask 5 Response (T6/R6)
    O2-->>O1: Subtask 3 Response (T4/R4)
    O1-->>C: Final Response (S1/T1/R1)
    C->>O1: Follow-on Invocation (S1/T1)
    O1->>O1: Generate New Request ID (R7)
    O1->>A2: Subtask 6 Invocation with Session ID S1, Task ID T3
    A2->>A2: Generate Request ID (R8)
    A2->>A2: Tool Use with HITL Required
    A2->>A2: Pause Task T3 Request R8
    A2-->>O1: HITL Required (T3/R8)
    O1->>O1: Pause Task T1 Request R7 Awaiting T3/R8
    O1-->>C: HITL Required, Request R8
    C->>RH: Approve Tool Use for Request R8
    RH->>A2: Resume Task T3 Request R8
    A2->>A2: Complete Tool Use/Request R8
    A2-->>O1: Subtask 6 Response (T3/R8)
    O1->>C: Final Response (S1/T1/R7)
```

### 1. Session ID (S)
- **Purpose**: Represents the highest-level grouping, corresponding to a continuous interaction or "conversation" with a client.
- **Scope**: It logically groups together multiple related tasks initiated by a user. For example, a user's entire interaction with a chatbot for a specific purpose would be one session.
- **Relevance**: While not directly used for the internal mechanics of agent/orchestrator state, it provides the essential client-facing context and allows clients to manage and reference logical units of work.

### 2. Task ID (T)
- **Purpose**: Represents a single, stateful "job" or goal that the system is asked to accomplish. A task can be simple (a single agent invocation) or complex (an orchestration involving multiple agents and sub-orchestrators).
- **State**: This is the lynchpin of the stateful architecture. The state associated with a Task ID must include:
    - **Interaction History**: A "chat history" or log of all invocations and responses related to the task. This is critical for providing context in follow-on invocations.
    - **Execution Trace**: A record of the steps taken, tools used, and intermediate results generated.
    - **Status**: The current state of the task (e.g., `Running`, `Paused`, `Completed`, `Failed`).
- **Lifecycle**: A task is created upon the initial invocation and persists until it is fully completed. Follow-on invocations from the client reference the same Task ID to leverage its history and state.

### 3. Request ID (R)
- **Purpose**: Represents a single, atomic attempt or invocation within a task. It provides the finest level of granularity for tracking and control.
- **Scope**: A unique Request ID is generated for each invocation of an agent or orchestrator. All actions performed within that invocation, including tool calls, belong to that single Request ID.
- **Criticality for HITL**: The Request ID is the key to enabling HITL. It allows the system to pause not just a general task, but the *specific agent invocation* that requires human approval. This prevents ambiguity and allows for precise control. When a `Resume Handler` approves an action, it targets the specific Request ID.
- **Benefits**:
    - **Idempotency**: If a resume signal is received multiple times, the system can check the status of the Request ID and prevent duplicate execution.
    - **Auditing**: Provides a detailed, auditable log of every single action taken by the system.

## Key Interaction Pattern: The "Cascading Pause" for HITL

The diagram illustrates the critical flow for handling Human-in-the-Loop scenarios:

1.  **Initiation**: An agent (A2) determines it needs to use a tool that requires human approval for a specific invocation (`Request R8`).
2.  **Agent Pause**: The agent pauses its current work on `Task T3` and sends a `HITL Required` message back to its caller (Orchestrator 1), specifying the `Task ID` and `Request ID` (`T3/R8`) that are paused.
3.  **Upstream Propagation**: The orchestrator (`O1`), upon receiving this message, pauses the parent task (`T1`) that was waiting on the result. It knows the subtask hasn't failed, but is merely pending external input.
4.  **Client Notification**: The orchestrator propagates the `HITL Required` message up to the original client, providing the specific `Request ID (R8)` that needs approval.
5.  **Resumption**: The client, through a `Resume Handler` or similar interface, sends an approval signal directly to the component that is paused—the agent (`A2`). This signal specifically targets `Request R8`.
6.  **Completion**: The agent receives the signal, resumes `Request R8`, completes its tool use, and sends its final response back up the chain, un-pausing the parent tasks along the way.

## Summary of Benefits

This S/T/R model provides a robust framework for building complex AI systems by delivering:
- **Clear Separation of Concerns**: Each primitive has a distinct and well-defined purpose.
- **Granular Control**: Enables precise actions like pausing and resuming specific requests.
- **Traceability & Auditability**: Creates a clear, hierarchical log of all actions taken.
- **Scalability**: Supports complex, nested workflows with multiple asynchronous actors.
- **Stateful Context**: Allows for rich, multi-turn interactions and follow-on requests.
