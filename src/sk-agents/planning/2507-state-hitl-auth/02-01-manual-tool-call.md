# Phase 2 - Refactor for Manual Tool Call

Teal Agents currently leverages Semantic Kernel's in-built functionality to
automatically perform agent tool calls. Unfortunately, the library does not include
required capability to allow for our code to intercept the tool call message response
from the LLM and perform any pre-requisite tasks prior to calling the tool.

## Preparation for HITL
We need to introduce human-in-the-loop (HITL) functionality wherein, for certain "high
risk" tool calls, we will pause the current interaction and respond to the calling
application with a specially crafted message which will instruct client to prompt the
user for explicit consent prior to proceeding with the tool call. To achieve this, we
will have to refactor some of the code, "de-abstracting" the portion of the Semantic
Kernel library where an agent performs tool calls.

## Reference Documentation
- `context/teal-agents-overview.md` - A reference of the overall structure and
  background of the Teal Agents project
- `context/state-refactor.md` - An overview of work that needs to be done to enable
  stateful agent interactions. This work is currently ongoing and as such, this branch
  of the code does not reflect any of this capability.
- `context/refinde-implementation-plan.md` - A detailed plan of how state will be
  implemented in the Teal Agents project (the actual work to-be-done based on the
  `state-refactor.md` document).
- `context/my-list.md` - This was my original plan for the refactoring to include state.
  it, along with the `state-refactor.md` document provided the basis for the work
  defined in `refined-implementation-plan.md`.
- `src/sk_agents/skagents/v1/sk_agent.py` - This is the specific file in the current
  implementation where agents are invoked. Within the file, in the `invoke` and
  `invoke_stream` methods, the Semantic Kernel library's agent methods are called and
  it is within these methods that tool calls are actually performed.
- `src/sk_agents/skagents/v1/sk_agent_v2.py` - A version of the `sk_agent.py` file that
  I directly refactored, using the Semantic Kernel library as a reference, to move the
  tool calling functionality up a level to where Teal Agents would be responsible for
  performing the tool calls. This file is not used in the current implementation, it
  was just an example of how the refactoring could be done.
- `chat_completion_agent.py` within the virtual environment - This is the Semantic
  Kernel file that contains the tool calling logic.  It was the basis for
  `sk_agent_v2.py`




