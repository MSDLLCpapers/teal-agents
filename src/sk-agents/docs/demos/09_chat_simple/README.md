# Chat-Only Agent

In addition to Sequential agents, there is also a chat-only type agent. The
difference between the two is that, with chat-only, there are no tasks in which
additional instructions can be provided. Rather, a chat-only agent expects input
of one of the following types:
* `BaseInput` - A simple text input
* `BaseInputWithUserContext` - A text input with user context
* `BaseMultiModalInput` - Input supporting both images and text

A chat-only agent will use the chat history that's provided and attempt to
perform any requested actions.

### Example Configuration

```yaml
apiVersion: skagents/v1
kind: Chat
description: >
  A simple chat agent
service_name: ChatBot
version: 0.1
input_type: BaseInput
spec:
  agent:
    name: default
    role: Default Agent
    model: gpt-4o-mini
    system_prompt: >
      You are a helpful assistant.
```
