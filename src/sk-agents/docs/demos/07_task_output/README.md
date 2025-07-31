# Multiple, Sequential Tasks

A Sequential Teal Agent allows you to perform multiple tasks, which should be
performed in sequence. Each task can have its own agent, or the same agent can
be shared by multiple tasks. Additionally, downstream tasks can leverage the
output from previous tasks to complete their instructions.

Similar to input variables, output from previous tasks can be injected in to the
instructions of a given task using the `{{}}` curly brace syntax. Each task has
unique variable name which is simply the name of the previously performed task
preceded by a `_`.


#### Example

In the following configuration example, we define a single agent that will
perform two tasks, in sequence, using the input provided by the consumer.

```yaml
apiVersion: skagents/v1
kind: Sequential
description: >
  Add numbers 1 & 2, then multiply the result by number 3 and add 10.
service_name: MathAgent
version: 0.1
input_type: NumbersInput
output_type: MathOutput
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
      description: Add two numbers
      instructions: >
        Add the following two numbers together
        {{number_1}} {{number_2}}
      agent: default
    - name: follow_on_task
      task_no: 2
      description: Perform a final operation
      instructions: >
        Multiply the result of the previous answer by {{number_3}} and then add
        10 to it.

        Previous operation:
        {{_action_task}}
      agent: default
```

NumbersInput is an object containing three fields:
```python
class NumbersInput(KernelBaseModel):
    number_1: int
    number_2: int
    number_3: int
```

In the first task, we simply add `number_1` and `number_2` together to get the
sum. In the second task, we multiply the result of the `action_task` by
`number_3` and add 10 to it.

**Note**: The `{{_action_task}}` variable is used to reference the output of the
`action_task` task. This is a special variable that is automatically created by
the Teal Agents Framework when a task is completed. The variable name is simply the
name of the task, preceded by an underscore.

**Additional Note**: The input to a downstream task that is a result from a
previous task will be the agent's raw response. Take care to phrase the follow
-on task's instructions in a way that the agent can understand the context.
