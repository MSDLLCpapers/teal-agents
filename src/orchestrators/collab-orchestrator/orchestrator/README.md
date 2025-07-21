# Teal Agent Platform - Collaboration Orchestrator
## Overview
The Collaboration Orchestrator provides a reusable orchestrator designed for
multi-agent collaboration scenarios where multiple agents work together to
accomplish complex tasks. Unlike the Assistant Orchestrator which is designed
for single-turn interactions, the Collaboration Orchestrator enables agents to
collaborate over multiple rounds of interaction.

The Collaboration Orchestrator supports two primary orchestration patterns:

### Core Components
1. **Team Orchestrator** - Facilitates group chat-style collaboration where
   multiple agents participate in a discussion managed by a team manager agent.
2. **Planning Orchestrator** - Enables structured workflow execution where
   agents collaborate according to predefined plans and can optionally include
   human-in-the-loop (HITL) interactions for plan approval.

### Supporting Services
1. **Manager Agent** - A special agent that coordinates the collaboration
   between other agents, making decisions about when to involve which agents.
2. **Task Agents** - Specialized agents that perform specific tasks within the
   collaborative workflow.
3. **Planning Agent** - An agent responsible for creating and managing execution
   plans in planning orchestration scenarios.
4. **Agent Catalog** - An instance of Kong which acts as a gateway for accessing
   agents, allowing the orchestrator to perform agent discovery.
5. **Redis** (Optional) - Used for storing pending plans when human-in-the-loop
   functionality is enabled.
6. **OpenTelemetry Gateway** (Optional) - A gateway which allows for the
   collection of telemetry data from the orchestrator and its supporting
   services.

## TL/DR;
Head over to the [example folder](./example/README.md) to see how to get a
working example running on your local machine with Docker Compose.

## Collaboration Orchestrator
The following section discusses the usage and configuration of the Collaboration
Orchestrator. The orchestrator is a configurable, reusable orchestrator that
provides core capability for deploying multi-agent collaborative applications.

### Environment Configuration
* TA_API_KEY - The API key for the Agent Catalog. Your orchestrator must be
  registered as a consumer on the Agent Catalog and must have permissions to all
  configured agents.
* TA_AGW_HOST (default: `localhost:8000`) - The `host:port` of the Agent
  Catalog
* TA_AGW_SECURE (default: `false`) - Whether or not the Agent Catalog
  should be accessed using HTTPS
* TA_SERVICE_CONFIG (default: `conf/config.yaml`) - The path to the
  configuration file for the orchestrator
* TA_REDIS_HOST (default: `localhost`) - The hostname of the Redis instance
  (required when human-in-the-loop is enabled)
* TA_REDIS_PORT (default: `6379`) - The port of the Redis instance
* TA_REDIS_DB (default: `0`) - The Redis database number to use

### Configuration File
A configuration file describing the orchestrator is required. The format varies
depending on the orchestration pattern:

#### Team Orchestrator Configuration
```yaml
apiVersion: skagents/v1
kind: TeamOrchestrator
description: >
  Group Chat Orchestrator for demo
service_name: CollaborationOrchestrator
version: 0.1
spec:
  max_rounds: 10
  manager_agent: TeamManagerAgent:0.1
  agents:
    - WikipediaAgent:0.1
    - ArxivSearchAgent:0.1
    - AssistantAgent:0.1
```

#### Planning Orchestrator Configuration
```yaml
apiVersion: skagents/v1
kind: PlanningOrchestrator
description: >
  Planning-based Orchestrator for structured workflows
service_name: CollaborationOrchestrator
version: 0.1
spec:
  human_in_the_loop: true
  planning_agent: PlanningAgent:0.1
  agents:
    - ResearchAgent:0.1
    - AnalysisAgent:0.1
    - SummaryAgent:0.1
```

### Configuration Parameters
* apiVersion - Always `skagents/v1`
* kind - Either `TeamOrchestrator` or `PlanningOrchestrator`
* description - A human-readable description of the orchestrator
* service_name - The name of the orchestrator
* version - The version of the orchestrator
* spec.max_rounds - (Team only) Maximum number of conversation rounds
* spec.manager_agent - (Team only) The name:version of the team manager agent
* spec.planning_agent - (Planning only) The name:version of the planning agent
* spec.human_in_the_loop - (Planning only) Whether to enable HITL functionality
* spec.agents - A list of name:version pairs of agents available for collaboration

### Supported Agents
The Collaboration Orchestrator imposes certain restrictions on the types of
agents which can be used within it:

#### Agent Discovery
An `openapi.json` file with a descriptive `description` field must be available
on the Agent Catalog at the path of `/<agent_name>/<agent_version>/openapi.json`.

#### Agent Input
All configured agents must support, as input, a JSON payload of the following
format:
```json
{
   "chat_history": [
      {
         "role": "user | assistant | system",
         "content": "The content of the message"
      },
      ...
   ]
}
```

#### Agent Output
All configured agents must support streaming output via the
`/<agent_name>/<agent_version>/stream` endpoint. Agents should accept a
websocket connection over this endpoint, perform their task, respond with
results, and then close the connection.

#### Manager Agent (Team Orchestrator)
The manager agent is responsible for coordinating the team collaboration:
- Decides which agent should respond next
- Determines when the conversation should end
- Manages the flow of information between agents

#### Planning Agent (Planning Orchestrator)
The planning agent creates execution plans for complex workflows:
- Analyzes user requests and creates structured plans
- Defines the sequence of agent interactions
- Handles plan modifications when human feedback is provided

## API Endpoints
The orchestrator exposes the following endpoints:

### Primary Interaction
* `POST /{service_name}/{version}` - Main orchestration endpoint that accepts
  multimodal input and returns streaming responses
* `GET /{service_name}/{version}/stream` - WebSocket endpoint for real-time
  streaming interactions

### Human-in-the-Loop (Planning Orchestrator only)
* `GET /hitl/pending-plans` - Retrieve pending plans awaiting approval
* `POST /hitl/approve-plan/{plan_id}` - Approve a pending plan
* `POST /hitl/reject-plan/{plan_id}` - Reject a pending plan with feedback

### Health and Documentation
* `GET /{service_name}/{version}/docs` - Interactive API documentation
* `GET /{service_name}/{version}/openapi.json` - OpenAPI specification

## Orchestration Patterns

### Team Orchestration
In team orchestration mode, agents participate in a group chat facilitated by
a manager agent. The manager determines:
- Which agent should respond to the current context
- When sufficient collaboration has occurred
- How to synthesize results from multiple agents

### Planning Orchestration
In planning orchestration mode, the workflow follows these steps:
1. User provides a request
2. Planning agent creates a structured execution plan
3. If HITL is enabled, the plan is stored and awaits human approval
4. Upon approval (or automatically if HITL is disabled), agents execute the plan
5. Results are collected and synthesized

## Human-in-the-Loop (HITL)
When enabled in planning orchestration, HITL allows human oversight of execution
plans:

### Plan Review Process
1. Planning agent creates an execution plan
2. Plan is stored in Redis with a unique ID
3. Human reviewers can inspect pending plans via the API
4. Plans can be approved, rejected, or modified
5. Approved plans proceed to execution

### Plan Management
Plans include:
- Step-by-step execution sequence
- Agent assignments for each step
- Expected inputs and outputs
- Dependencies between steps

## Additional Configuration
Both orchestration patterns support additional configuration options for
telemetry and monitoring:

* TA_TELEMETRY_ENABLED (default: false) - Whether or not telemetry should be
  collected
* TA_OTEL_ENDPOINT (default: None) - The OpenTelemetry gateway endpoint to
  which telemetry data should be sent