# Teal Agent Platform - Assistant Orchestrator - Hybrid
## Overview
The Assistant Orchestrator provides a reusable orchestrator and supporting
services meant to be used for chat-style applications where multiple different
agents are able to provide users with the ability to perform various tasks.

The Assistant Orchestrator is comprised of two core components and a number of
supporting services

### Core Components
1. **Assistant Orchestrator Hybrid** - The orchestrator itself, which is responsible
   for managing client connections, handling configured authentication,
   maintaining chat history, and routing messages to the appropriate agent or a
   configured fallback agent.
2. **Orchestrator Services** (Optional) - Services which provide client
   authentication, and persistent storage of chat history - Uses AO service

### Supporting Services
1. **Agent Selector Agent** - A special agent which leverages the core agent
   framework to select one of the configured agents to handle a user's request.
2. **Fallback Agent** - An agent which is used when no other agent is able to
   handle a user's request.
3. **Agent Catalog** - An instance of Kong which acts as a gateway for accessing
   agents, allowing the orchestrator to perform discovery.
4. **DynamoDB** (Optional) - High performance persistent storage for 
   authentication tokens and chat history.
5. **OpenTelemetry Gateway** (Optional) - A gateway which allows for the
   collection of telemetry data from the orchestrator and its supporting
   services.

### Example Architecture
At a high level, an implementation of this orchestrator will look something
like:
WIP

## TL/DR;
Head over to the [example folder](./example/README.md) to see how to get a
working example running on your local machine.

## Assistant Orchestrator
The following section discusses the usage and configuration of the Agent
Orchestrator. If you're interested in learning more about how to run it locally,
check out the [README.md](./orchestrator/README.md).

The Assistant Orchestrator Hybrid is a configurable, reusable orchestrator that
provides all the core capability for deploying a chat-style agent application.
When deploying, it supports a number of required and optional features which are
configured via both environment variables and a configuration file.

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
* TA_AUTH_ENABLED (default: `true`) - Whether or not client connections should
  be authenticated. Authentication can be configured to use either `internal` or
  `external` (see next option). If changed to `false`, all users will be
  identified as `default` for the purposes of telemetry and chat history.
* TA_SERVICES_TYPE (default: `internal`) - Can be set to either `internal` or
  `external`. If `internal`, is used, then no authentication is actually
  performed, and all users are identified as `default`. If `external` is used,
  then you must have a running instance of the Assistant Orchestrator Services
  and it must be configured in subsequent environment variables.
* TA_SERVICES_TYPE (default: None) - If `external` is chosen as the
  service type, then this value must be set to the `prot://host:port` of the
  running instance of the service.
* TA_SERVICES_TOKEN (default: None) - If your instance of Assistant
  Orchestrator Services is configured to require a token for authentication,
  then this value must be set to the token.

### Configuration File
In addition to the environment variables, a configuration file in the following
forma, describing the orchestrator is required.
```yaml
apiVersion: skagents/v1
kind: AssistantOrchestrator
description: >
  Assistant Orchestrator for demo chat app
service_name: DemoAgentOrchestrator
version: 0.1
spec:
  fallback_agent: GeneralAgent:0.1
  agent_chooser: AgentSelectorAgent:0.1
  agents:
    - MathAgent:0.1
    - WeatherAgent:0.1
    - ProcessAgent:0.1
```

* apiVersion - Always `skagents/v1`
* kind - Always `AssistantOrchestrator`
* description - A human-readable description of the orchestrator
* service_name - The name of the orchestrator
* version - The version of the orchestrator
* spec.fallback_agent - The name:version (as registered with the agent catalog)
  of the agent to-be-used when none of the other, configured agents satisfy a
  user request
* spec.agent_chooser - The name:version (as registered with the agent catalog)
  of the agent which will be used to select the appropriate agent used to handle
  a specific user request
* spec.agents - A list of name:version pairs (as registered with the agent
  catalog) of the agents which can be used to handle user requests

### Supported Agents
As mentioned previously, an orchestrator type will impose certain restrictions
on the types of agents which can be used within it. For the Assistant
Orchestrator, the following restrictions are in place:

#### Configured Agent Discovery
An `openapi.json` file with a very descriptive `description` field must be
available on the Agent Catalog at the path of
`/<agent_name>/<agent_version>/openapi.json`. Note, the description must be
robust to ensure that this agent is chosen for appropriate user requests.

#### Configured Agent Input
All configured agents and the fallback agent must support, as input, a JSON
payload of the following format:
```json
{
   "chat_history": [
      {
         "role": "`user` or `assistant` only",
         "content": "The content of the message"
      },
      ...
   ]
}
```
Note: If using the Core Agent Framework, this input type is built-in as
InputType `BaseInput`.

#### Configured Agent Output
All configured agents and the fallback agent must support streaming output via
the `/<agent_name>/<agent_version>/stream` endpoint. It is expected that the
agent will accept a websocket connection over this endpoint, will perform a
single-turn interaction, respond with the results, and then close the
connection.

#### Agent Selector Agent
The Agent Selector Agent is a special agent which is used to select the agent
which will handle a user request. For this agent, different requirements are in
place. Generally, you should use one of the standard Agent Selector Agents
for your use case.

##### Agent Chooser Input
The Agent Selector Agent must support, as input, a JSON payload of the following
format:

```json
{
   "conversation_history": {
      "conversation_id": "A unique identifier for the conversation",
      "agent_list": [
         {
            "name": "The name of the agent in `name:version` syntax",
            "description": "The description of the agent"
         },
         ...
      ],
      "history": [
         {
            "content": "The content of the message",
            "sender or recipient": "The name of the agent with whom the message was exchanged (either sent to or received from)"
         },
         ...
      ],
      
   }
}
```

##### Agent Chooser Output
The Agent Selector Agent must respond with structured output in the following
JSON format:
```json
{
   "token_usage": {
      "completion_tokens": NN,
      "prompt_tokens": NN,
      "total_tokens": NN
   },
   "output_raw": "A JSON-encoded string described below",
   "output_pydantic": null
}
```

###### output_raw Format
We used `output_raw` instead of `output_pydantic` (enforcing structured output)
to decrease the amount of time spent selecting the agent for the user request.
As such, it is critical that the agent respond with well-structured JSON in the
format below. You can coerce the agent to respond appropriately with well-formed
instructions.
```json
{
   "agent_name": "The selected agent from the list of those provided",
   "confidence": "high|medium|low - The confidence in the prediction",
   "is_followup": "true|false - Whether or not this is a follow-up request"
}
```

## Assistant Orchestrator Services
The following section discusses the usage and configuration of the Orchestrator
Services. If you're interested in learning more about how to run it locally,
check out the [README.md](./services/README.md).

The Assistant Orchestrator Services are an optional set of services which can be
deployed alongside an Assistant Orchestrator which provides authentication, chat
history persistence services (used for re-connect scenarios), and user context
management.

Assistant Orchestrator supports both websocket and RESTful interactions (coming
soon). The flow for conversations is slightly different, depending on which
strategy is chosen, but the flow for both can be illustrated as follows:

![Orchestrator-Services Flow](/assets/ao-services-flow.png)

Note: Currently persistent services are only able to use DynamoDB. This needs to
be extended in the future to support other storage options.


### Authentication
By default, there is no authentication performed by the Assistant Orchestrator.
In real use cases, a custom authentication scheme must be implemented and
configured. To read more about how to enable authentication for your use case,
see the [custom authentication README.md](./services/auth/README.md).

#### Websocket Authentication Process
Due to limitations in browser implementations of websockets, authentication
requires a two-step process. First, the invoking application will need to
request a "ticket" from the Orchestrator Services by invoking the Create Ticket
endpoint `/services/v1/{orchestrator name}/ticket`. This endpoint will perform
any configured, required authentication, and return a UUID `ticket`. This ticket
can then be used to initiate the websocket connection to the Orchestrator at the
`/{orchestrator name}/{orchestrator version}/stream/{ticket}` endpoint.

#### RESTful Authentication Process
Since the RESTful invocation treats each interaction as an end-to-end, single
step process, multiple steps are not required. Required authentication details
are sent along with the invocation request and authentication is performed using
the configured authentication scheme.

### Chat History
Chat history for a user of the Assistant Orchestrator is persisted. The primary
use case for this is to allow for re-connect scenarios of the websocket
interaction flow.

If the client is disconnected from the websocket, but wishes to resume a
previous conversation, it will still need to re-authenticate and receive a new
ticket. However, when initiating the new websocket connection, it can send the
`resume=true` query parameter which will cause the new connection to reload all
history from the immediately preceding conversation. This can be done multiple
times and history from all conversations will be loaded.

### User Context
Persistent user context can be stored by the Orchestrator Services. This context
can then be used by the Orchestrator's interactions with the various agents to
provide a more personalized experience for the user. Persistent user context
supports all the typical CRUD operations:

* Create - `POST /services/v1/{orchestrator name}/users/{user ID}/context`
* Read - `GET /services/v1/{orchestrator name}/users/{user ID}/context`
* Update - `PUT /services/v1/{orchestrator name}/users/{user ID}/context/{key}`
* Delete - `DELETE /services/v1/{orchestrator name}/users/{user ID}/context/{key}`

For more information about user context, see [user-context.md](./doc/user-context.md).

### Environment Configuration
* TA_DYNAMO_HOST (default: None) - For local testing, the `prot://host:port`
  of the local DynamoDB instance
* TA_KONG_ENABLED (default: false) - If the user is connecting through Kong,
  set this to `true` when you're also verifying client IP addresses to ensure
  the correct IP address is captured when requesting a ticket
* TA_VERIFY_IP (default: false) - If set to true, authentication will
  additionally perform an IP verification to ensure the client is connecting to
  chat from the same IP from which the ticket was requested (websockets only).
* TA_ENVIRONMENT (default: `dev`) - When set to `local`, services will create
  required DynamoDB tables when started. If set to anything other than `local`
  the tables must already exist.
* TA_DYNAMO_TABLE_PREFIX (default: '') - A prefix to be added to the DynamoDB
  table names. This is useful when running multiple instances of the services
  for different environments.
* TA_DYNAMO_REGION (default: `us-east-1`) - The AWS region in which the DynamoDB
  instance is running
* TA_CUSTOM_AUTH_ENABLED - Set to `true` to activate your custom
  authentication
* TA_CUSTOM_AUTH_MODULE - The relative path to the python module containing
  your custom authentication implementation (payload and class)
* TA_CUSTOM_AUTHENTICATOR - The name of your implementation of the\
  `Authenticator` class
* TA_CUSTOM_AUTH_REQUEST - The name of your implementation of the request
  payload class


## Additional Configuration for Both
In addition to the specific environment variables described above, both the
Orchestrator and Services support the following, additional configuration
options for robust telemetry capture:
* TA_TELEMETRY_ENABLED (default: false) - Whether or not telemetry should be
  collected
* TA_OTEL_ENDPOINT (default: None) - The OpenTelemetry gateway endpoint to
  which telemetry data should be sent