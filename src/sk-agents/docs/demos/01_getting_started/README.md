# Configuring an Agent

All agents are configured using a YAML configuration file. For a very simple
agent that simply interacts with the user using a specified LLM, your agent
config file might look something like:

```yaml
apiVersion: skagents/v1
kind: Sequential
description: >
  A simple chat agent
service_name: ChatBot
version: 0.1
input_type: BaseInput
spec:
  agents:
    - name: default
      role: Default Agent
      model: gpt-4o
      system_prompt: >
        You are a helpful assistant.
  tasks:
    - name: action_task
      task_no: 1
      description: Chat with user
      instructions: >
        Work with the user to assist them in whatever they need.
      agent: default
```

An agent configuration file can contain the following elements:
* apiVersion - At present, this should always be `skagents/v1`
* kind - The way in which an agent will execute its tasks. Currently only the
  value `Sequential` is supported, which means, for each invocation, the agent
  will execute all tasks in the defined order.
* description (optional) - A description of the agent
* service_name - The name of the agent (and thus its service). This, in
  combination with the version will make up the agent's REST and streaming
  endpoints. In this example, said endpoints would be
  * `/ChatBot/0.1`
  * `/ChatBot/0.1/stream`
* version - The version of the agent (see above)
* input_type - The payload format for requests to this agent (more on this
  later)
* output_type (optional - not shown) - The payload format for responses from
  this agent (more on this later)
* spec - Agent and task configuration
* agents - A list of agents that can be used by tasks
  * name - The name of the agent
  * role - The role/description of the agent
  * model - The LLM model to use
  * system_prompt - A system prompt for the agent
* tasks - A list of tasks to be executed by the agent
  * name - The name of the task
  * task_no - The order in which the task should be executed
  * description - A description of the task
  * instructions - Instructions for the task
  * agent - The agent to use for the task (must match agent defined in the
    agents section)

## Currently available models
The models currently available for agent configuration include:
* gpt-4o (Not for MSD usage)
* gpt-4o-mini (Not for MSD usage)
