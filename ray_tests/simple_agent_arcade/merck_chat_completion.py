"""
Custom Chat Completion Client for Merck GPT API.

This module provides a Semantic Kernel-compatible chat completion client
that integrates with Merck's internal GPT API endpoint.
"""

import json
import logging
from typing import Any, AsyncIterable, Optional

import httpx
from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.open_ai_prompt_execution_settings import (
    OpenAIChatPromptExecutionSettings,
)
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.function_result_content import FunctionResultContent
from semantic_kernel.contents.streaming_chat_message_content import StreamingChatMessageContent
from semantic_kernel.contents.text_content import TextContent
from semantic_kernel.kernel import Kernel


logger = logging.getLogger(__name__)


class MerckChatCompletion(ChatCompletionClientBase):
    """
    A Semantic Kernel chat completion client for Merck's GPT API.
    
    This client wraps Merck's internal API endpoint and provides the standard
    Semantic Kernel interface for chat completions.
    """

    def __init__(
        self,
        service_id: str,
        api_key: str,
        api_root: str,
        model_name: str,
        async_client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Initialize the Merck Chat Completion client.

        Args:
            service_id: Unique identifier for this service instance
            api_key: Merck X-Merck-APIKey for authentication
            api_root: Base URL for the Merck API (e.g., https://iapi-test.merck.com/gpt/v2)
            model_name: Model identifier (e.g., gpt-5-2025-08-07)
            async_client: Optional httpx AsyncClient for connection pooling
        """
        super().__init__(service_id=service_id, ai_model_id=model_name)
        # Use object.__setattr__ to bypass Pydantic validation for custom attributes
        object.__setattr__(self, '_api_key', api_key)
        object.__setattr__(self, '_api_root', api_root.rstrip("/"))
        object.__setattr__(self, '_model_name', model_name)
        object.__setattr__(self, '_client', async_client or httpx.AsyncClient(timeout=120.0))

    async def get_chat_message_contents(
        self,
        chat_history: ChatHistory,
        settings: OpenAIChatPromptExecutionSettings,
        kernel: Kernel = None,
        **kwargs: Any,
    ) -> list[ChatMessageContent]:
        """
        Get chat message contents from the Merck API.

        Args:
            chat_history: The chat history to send to the API
            settings: Execution settings (temperature, max_tokens, etc.)
            kernel: Optional Semantic Kernel instance for function calling support
            **kwargs: Additional arguments

        Returns:
            List of ChatMessageContent objects containing the response
        """
        # Convert chat history to API format
        messages = self._chat_history_to_messages(chat_history)

        # Build request payload
        payload = {
            "messages": messages,
        }

        # Add function calling support
        if kernel and settings.function_choice_behavior:
            tools = self._build_tools_from_kernel(kernel)
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"
                logger.debug(f"Added {len(tools)} tools to API request")

        # Only add temperature if explicitly set to 1 (the only supported value)
        temperature = getattr(settings, 'temperature', None)
        if temperature is not None and temperature == 1:
            payload["temperature"] = temperature

        max_tokens = getattr(settings, 'max_tokens', None)
        if max_tokens is not None and max_tokens > 0:
            payload["max_completion_tokens"] = max_tokens

        # Add any additional parameters
        top_p = getattr(settings, 'top_p', None)
        if top_p is not None:
            payload["top_p"] = top_p
        
        frequency_penalty = getattr(settings, 'frequency_penalty', None)
        if frequency_penalty is not None:
            payload["frequency_penalty"] = frequency_penalty
        
        presence_penalty = getattr(settings, 'presence_penalty', None)
        if presence_penalty is not None:
            payload["presence_penalty"] = presence_penalty
        
        # Add reasoning_effort for o1-style models (gpt-5, etc.)
        reasoning_effort = getattr(settings, 'reasoning_effort', None)
        if reasoning_effort is not None:
            payload["reasoning_effort"] = reasoning_effort

        # Make API request
        url = f"{self._api_root}/{self._model_name}/chat/completions?api-version=2024-12-01-preview"
        headers = {
            "Content-Type": "application/json",
            "X-Merck-APIKey": self._api_key,
        }

        try:
            response = await self._client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()

            # Extract the message content
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]["message"]

                # Check for tool calls (function calling)
                if "tool_calls" in choice and choice["tool_calls"]:
                    logger.debug(f"Received {len(choice['tool_calls'])} tool calls from API")
                    # Return FunctionCallContent for each tool call
                    items = []
                    for tool_call in choice["tool_calls"]:
                        func_name = tool_call["function"]["name"]
                        func_args = tool_call["function"]["arguments"]
                        logger.debug(f"Tool call: {func_name}, arguments: {func_args}")

                        items.append(FunctionCallContent(
                            id=tool_call["id"],
                            name=func_name,
                            arguments=func_args
                        ))

                    return [
                        ChatMessageContent(
                            role="assistant",
                            items=items,
                            ai_model_id=self._model_name,
                            metadata={
                                "usage": result.get("usage", {}),
                                "finish_reason": choice.get("finish_reason"),
                            },
                        )
                    ]

                # Regular text response (no tool calls)
                content = choice.get("content", "")

                # Create ChatMessageContent response
                return [
                    ChatMessageContent(
                        role="assistant",
                        content=content,
                        ai_model_id=self._model_name,
                        metadata={
                            "usage": result.get("usage", {}),
                            "finish_reason": choice.get("finish_reason"),
                        },
                    )
                ]
            else:
                raise ValueError("No response from API")

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error calling Merck API: {e.response.status_code} - {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Error calling Merck API: {str(e)}")
            raise

    async def get_streaming_chat_message_contents(
        self,
        chat_history: ChatHistory,
        settings: OpenAIChatPromptExecutionSettings,
        **kwargs: Any,
    ) -> AsyncIterable[list[StreamingChatMessageContent]]:
        """
        Get streaming chat message contents from the Merck API.

        Note: This is a fallback implementation that calls the non-streaming API.
        True streaming support would require server-sent events support in the Merck API.

        Args:
            chat_history: The chat history to send to the API
            settings: Execution settings
            **kwargs: Additional arguments

        Yields:
            Lists of StreamingChatMessageContent objects
        """
        # For now, use non-streaming and yield the result
        # In a production implementation, you would use SSE streaming if supported
        messages = await self.get_chat_message_contents(chat_history, settings, **kwargs)
        
        for message in messages:
            yield [
                StreamingChatMessageContent(
                    role=message.role,
                    content=message.content,
                    choice_index=0,
                    ai_model_id=self._model_name,
                )
            ]

    def _chat_history_to_messages(self, chat_history: ChatHistory) -> list[dict]:
        """
        Convert Semantic Kernel ChatHistory to API message format.

        Handles different message types:
        - Regular messages: role + content
        - Assistant messages with tool_calls: role + tool_calls array
        - Tool messages: role + content + tool_call_id (from FunctionResultContent)

        Args:
            chat_history: The chat history to convert

        Returns:
            List of message dictionaries in API format
        """
        messages = []
        for message in chat_history.messages:
            role = message.role.value if hasattr(message.role, "value") else str(message.role)

            msg_dict = {"role": role}

            # Check if message contains items (function calls or function results)
            if hasattr(message, 'items') and message.items:
                # Check for FunctionCallContent (assistant requesting tool calls)
                function_calls = [item for item in message.items if isinstance(item, FunctionCallContent)]
                if function_calls:
                    # Assistant message with tool calls
                    msg_dict["tool_calls"] = []
                    for fc in function_calls:
                        msg_dict["tool_calls"].append({
                            "id": fc.id,
                            "type": "function",
                            "function": {
                                "name": fc.name,
                                "arguments": fc.arguments
                            }
                        })
                    # tool_calls messages don't have content in OpenAI format
                    msg_dict["content"] = None
                    messages.append(msg_dict)
                    continue

                # Check for FunctionResultContent (tool results)
                function_results = [item for item in message.items if isinstance(item, FunctionResultContent)]
                if function_results:
                    # Tool message with function result
                    # Each FunctionResultContent becomes a separate tool message
                    for fr in function_results:
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": fr.id,  # FunctionResultContent has the id from original call
                            "content": str(fr.result) if fr.result is not None else ""
                        }
                        messages.append(tool_msg)
                    continue

                # Regular message with other content
                msg_dict["content"] = message.content
            else:
                # Regular text message
                msg_dict["content"] = message.content

            messages.append(msg_dict)

        return messages

    def _build_tools_from_kernel(self, kernel: Kernel) -> list[dict]:
        """
        Extract tool definitions from kernel plugins.

        Args:
            kernel: The Semantic Kernel instance containing registered plugins

        Returns:
            List of tool definitions in OpenAI format
        """
        tools = []

        for plugin_name, plugin in kernel.plugins.items():
            if hasattr(plugin, 'functions'):
                for func_name, func in plugin.functions.items():
                    # Build OpenAI-compatible tool definition
                    tool_def = {
                        "type": "function",
                        "function": {
                            "name": f"{plugin_name}-{func_name}",
                            "description": func.description or "No description available",
                            "parameters": self._extract_parameters(func)
                        }
                    }
                    tools.append(tool_def)
                    logger.debug(f"Added tool: {plugin_name}-{func_name}")

        return tools

    def _extract_parameters(self, func) -> dict:
        """
        Extract parameter schema from function metadata.

        Args:
            func: The Semantic Kernel function object

        Returns:
            JSON schema for function parameters
        """
        params_schema = {
            "type": "object",
            "properties": {},
            "required": []
        }

        if hasattr(func, 'metadata') and func.metadata and hasattr(func.metadata, 'parameters'):
            for param in func.metadata.parameters:
                params_schema["properties"][param.name] = {
                    "type": self._python_type_to_json_type(param.type_),
                    "description": param.description or ""
                }
                if param.is_required:
                    params_schema["required"].append(param.name)

        return params_schema

    @staticmethod
    def _python_type_to_json_type(python_type: str) -> str:
        """
        Convert Python type string to JSON schema type.

        Args:
            python_type: Python type as string (e.g., "str", "int")

        Returns:
            Corresponding JSON schema type
        """
        type_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
            "list": "array",
            "dict": "object"
        }
        return type_map.get(python_type, "string")

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close the HTTP client."""
        await self._client.aclose()
