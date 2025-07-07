# Teal Agent Platform - Orchestrators
## Overview
While individual agents can be created and leveraged by applications, to realize
the full potential of agentic architectures, you'll eventually want to
incorporate multiple agents, working together. To achieve this, you will require
some sort of agent orchestration.

The type of orchestration you need will be highly dependent on the interaction
model of your use case. As such, no single orchestrator will accommodate all
requirements and thus, there will exist multiple styles of orchestrators.

Additionally, these different styles will, necessarily, impose restrictions on
the types of agents which can be used within them. As an example, let's look at
two potential use cases for agent orchestration:

1. A chat-style system wherein users are leveraging agents to perform various
   tasks.
2. A multi-step business process which combines many steps, some which will be
   performed by agents, and others which will be performed by humans or other
   non-agentic technologies.

In the case of the former, we can see how the agents which are being
orchestrated would need adhere to certain specifications, like:
* The ability to receive chat history to understand the context of the current
  task.
* The ability to stream output to minimize the time-to-first-token, to provide
  better overall responsiveness (since user experience is critical).

In the case of the latter, it's implied that certain tasks are done by agents
while others are not. As such, different restrictions might be placed on the
needed orchestrator, for example:
* The ability to maintain long-running state of an overall system.
* The ability to accept payloads in a structured format using a REST-style API.

Because of this variability, and unlike the core framework, the Agent Platform
will not attempt to solve all orchestration use cases using a single pattern,
but rather, provide different orchestrators which can be used for different
scenarios, appropriately.

## Orchestrator Types
[Assistant Orchestrator](assistant-orchestrator/README.md)

[Collab Orchestrator](collab-orchestrator/orchestrator/README.md)