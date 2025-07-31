# Implementation Plan for Manual Tool Calling (with Code)

This document outlines the plan to refactor the agent invocation process to allow for manual interception of tool calls, as described in `context/manual-tool-call.md`. This change is a prerequisite for implementing Human-in-the-Loop (HITL) functionality.

The implementation will follow the "de-abstracted" pattern prototyped in `src/sk_agents/skagents/v1/sk_agent_v2.py` and will be integrated into the new stateful API version `tealagents/v1alpha1`.

## 1. High-Level Strategy

We will replace the high-level `agent.invoke()` and `agent.invoke_stream()` calls with a manual orchestration of the LLM interaction within our `Agent`. This provides a clear interception point to inspect tool calls before they are executed.

## 2. New HITL Placeholder Module

A new placeholder module will be created to establish a clean interception point for future HITL logic.

**File to Create**: `src/sk_agents/tealagents/v1alpha1/hitl_manager.py`

```python
# src/sk_agents/tealagents/v1alpha1/hitl_manager.py
from semantic_kernel.contents.function_call_content import FunctionCallContent

def check_for_intervention(tool_call: FunctionCallContent) -> bool:
    """
    Placeholder for HITL logic. In the future, this will check
    if the tool call requires user consent based on configured policies.

    Returns False for now, allowing all calls to proceed without interruption.
    """
    # TODO: Implement actual policy checks for high-risk tools.
    print(f"HITL Check: Intercepted call to {tool_call.plugin_name}.{tool_call.function_name}. Allowing to proceed.")
    return False
```

## 3. Refactoring the Agent Handler

The core changes will be in the `Agent`.

**File to Modify**: `src/sk_agents/tealagents/v1alpha1/agent.py`

### 3.1. Add Imports and Helper Method

We will add necessary imports and the `_invoke_function` helper method, adapted directly from `sk_agent_v2.py`.

```python
# Add to imports at the top of src/sk_agents/tealagents/v1alpha1/agent.py
import asyncio
from functools import reduce

from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.function_result_content import FunctionResultContent
from semantic_kernel.contents.streaming_chat_message_content import StreamingChatMessageContent

# Import the new HITL placeholder
from sk_agents.hitl import hitl_manager

# ... existing class definition for Agent ...

    # Add this helper method inside the TealAgentsV1Alpha1Handler class
    async def _invoke_function(self, kernel: "Kernel", fc_content: FunctionCallContent) -> FunctionResultContent:
        """Helper to execute a single tool function call."""
        function = kernel.get_function(
            fc_content.plugin_name,
            fc_content.function_name,
        )
        function_result = await function(kernel, fc_content.to_kernel_arguments())
        return FunctionResultContent.from_function_call_content_and_result(
            fc_content, function_result
        )
```

### 3.2. Updated `invoke` Method (Non-Streaming)

The `invoke` method will be replaced with the following code to manually handle the tool-calling loop.

```python
# Replace the existing 'invoke' method in TealAgentsV1Alpha1Handler
async def invoke(self, history: ChatHistory) -> AsyncIterable[ChatMessageContent]:
    kernel = self.agent.kernel
    arguments = self.agent.arguments
    chat_completion_service, settings = kernel.select_ai_service(
        arguments=arguments, type=ChatCompletionClientBase
    )
    assert isinstance(chat_completion_service, ChatCompletionClientBase)

    # Initial call to the LLM
    response_list = await chat_completion_service.get_chat_message_contents(
        chat_history=history,
        settings=settings,
        kernel=kernel,
        arguments=arguments,
    )

    function_calls = []
    # Separate content and tool calls
    for response in response_list:
        # A response may have multiple items, e.g., multiple tool calls
        fc_in_response = [item for item in response.items if isinstance(item, FunctionCallContent)]

        if fc_in_response:
            history.add_message(response) # Add assistant's message to history
            function_calls.extend(fc_in_response)
        else:
            # If no function calls, it's a direct answer
            yield response

    # If tool calls were returned, execute them
    if function_calls:
        # --- INTERCEPTION POINT ---
        for fc in function_calls:
            hitl_manager.check_for_intervention(fc)
            # In the future, a `True` return would trigger a pause flow.

        # Execute all functions in parallel
        results = await asyncio.gather(
            *[self._invoke_function(kernel, fc) for fc in function_calls]
        )

        # Add results to history
        for result in results:
            history.add_message(result.to_chat_message_content())

        # Make a recursive call to get the final response from the LLM
        async for final_response in self.invoke(history):
            yield final_response
```

### 3.3. Updated `invoke_stream` Method (Streaming)

The `invoke_stream` method will be replaced to handle streaming and tool calls correctly.

```python
# Replace the existing 'invoke_stream' method in TealAgentsV1Alpha1Handler
async def invoke_stream(self, history: ChatHistory) -> AsyncIterable[StreamingChatMessageContent]:
    kernel = self.agent.kernel
    arguments = self.agent.arguments
    chat_completion_service, settings = kernel.select_ai_service(
        arguments=arguments, type=ChatCompletionClientBase
    )
    assert isinstance(chat_completion_service, ChatCompletionClientBase)

    all_responses = []
    # Stream the initial response from the LLM
    async for response_list in chat_completion_service.get_streaming_chat_message_contents(
        chat_history=history,
        settings=settings,
        kernel=kernel,
        arguments=arguments,
    ):
        for response in response_list:
            all_responses.append(response)
            if response.content:
                yield response # Yield content chunks to the client immediately

    # Aggregate the full response to check for tool calls
    if not all_responses:
        return

    full_completion: StreamingChatMessageContent = reduce(lambda x, y: x + y, all_responses)
    function_calls = [
        item
        for item in full_completion.items
        if isinstance(item, FunctionCallContent)
    ]

    # If tool calls are present, execute them
    if function_calls:
        history.add_message(message=full_completion.to_chat_message_content())

        # --- INTERCEPTION POINT ---
        for fc in function_calls:
            hitl_manager.check_for_intervention(fc)

        # Execute functions in parallel
        results = await asyncio.gather(
            *[self._invoke_function(kernel, fc) for fc in function_calls]
        )

        # Add results to history
        for result in results:
            history.add_message(result.to_chat_message_content())

        # Make a recursive call to get the final streamed response
        async for final_response_chunk in self.invoke_stream(history):
            yield final_response_chunk
```

## 4. Testing Strategy

The testing strategy remains the same as the previous plan, but the tests in `tests/test_tealagents_handler.py` will now be written against this specific implementation, verifying:

1.  Simple chat works without regression.
2.  Tool calls are correctly identified and executed.
3.  The `hitl_manager.check_for_intervention` function is called for each tool invocation.
4.  The final response after tool execution is correct for both streaming and non-streaming modes.
