import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterable
from datetime import datetime
from functools import reduce

from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import ChatMessageContent, ImageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.function_result_content import FunctionResultContent
from semantic_kernel.contents.streaming_chat_message_content import StreamingChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from sk_agents.authorization.dummy_authorizer import DummyAuthorizer
from sk_agents.exceptions import AgentInvokeException, AuthenticationException, PersistenceLoadError
from sk_agents.extra_data_collector import ExtraDataCollector, ExtraDataPartial
from sk_agents.persistence.in_memory_persistence_manager import InMemoryPersistenceManager
from sk_agents.ska_types import BaseConfig, BaseHandler, ContentType, TokenUsage
from sk_agents.tealagents.models import (
    AgentTask,
    AgentTaskItem,
    HitlResponse,  # Make sure this is imported or defined
    MultiModalItem,
    TealAgentsPartialResponse,
    TealAgentsResponse,
    UserMessage,
    RejectedToolResponse
)
from sk_agents.tealagents.v1alpha1 import hitl_manager
from sk_agents.tealagents.v1alpha1.agent.config import Config
from sk_agents.tealagents.v1alpha1.agent_builder import AgentBuilder
from sk_agents.tealagents.v1alpha1.utils import get_token_usage_for_response, item_to_content
from sk_agents.tealagents.v1alpha1.sk_agent import SKAgent

logger = logging.getLogger(__name__)


class TealAgentsV1Alpha1Handler(BaseHandler):
    def __init__(self, config: BaseConfig, agent_builder: AgentBuilder):
        self.version = config.version
        self.name = config.name
        if hasattr(config, "spec"):
            self.config = Config(config=config)
        else:
            raise ValueError("Invalid config")
        self.agent_builder = agent_builder
        self.state = InMemoryPersistenceManager()
        self.authorizer = DummyAuthorizer()

    async def _invoke_function(
        self, kernel, fc_content: FunctionCallContent
    ) -> FunctionResultContent:
        """Helper to execute a single tool function call."""
        function = kernel.get_function(
            fc_content.plugin_name,
            fc_content.function_name,
        )
        function_result = await function(kernel, fc_content.to_kernel_arguments())
        return FunctionResultContent.from_function_call_content_and_result(
            fc_content, function_result
        )

    @staticmethod
    def _augment_with_user_context(inputs: UserMessage | None, chat_history: ChatHistory) -> None:
        if inputs.user_context:
            content = "The following user context was provided:\n"
            for key, value in inputs.user_context.items():
                content += f"  {key}: {value}\n"
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, items=[TextContent(text=content)])
            )

    @staticmethod
    def _configure_agent_task(
        session_id: str,
        user_id: str,
        task_id: str,
        role: str,
        request_id: str,
        inputs: UserMessage,
        status: str,
    ) -> AgentTask:
        agent_items = []
        for item in inputs.items:
            task_item = AgentTaskItem(
                task_id=task_id, role=role, item=item, request_id=request_id, updated=datetime.now()
            )
            agent_items.append(task_item)

        agent_task = AgentTask(
            task_id=task_id,
            session_id=session_id,
            user_id=user_id,
            items=agent_items,
            created_at=datetime.now(),
            last_updated=datetime.now(),
            status=status,
        )
        return agent_task

    def authenticate_user(self, token: str) -> str:
        try:
            user_id = self.authorizer.authorize_request(auth_header=token)
            return user_id
        except Exception as e:
            raise AuthenticationException(
                message=f"Unable to authenticate user, exception message: {e}"
            ) from e

    @staticmethod
    def handle_state_id(inputs: UserMessage) -> tuple[str, str, str]:
        if inputs.session_id:
            session_id = inputs.session_id
        else:
            session_id = str(uuid.uuid4().hex)

        if inputs.task_id:
            task_id = inputs.task_id
        else:
            task_id = str(uuid.uuid4().hex)

        request_id = str(uuid.uuid4().hex)

        return session_id, task_id, request_id

    async def _manage_incoming_task(
        self, task_id: str, session_id: str, user_id: str, request_id: str, inputs: UserMessage
    ) -> AgentTask:
        try:
            agent_task = await self.state.load(task_id)
            return agent_task
        except PersistenceLoadError:
            agent_task = TealAgentsV1Alpha1Handler._configure_agent_task(
                session_id=session_id,
                user_id=user_id,
                task_id=task_id,
                role="user",
                request_id=request_id,
                inputs=inputs,
                status="Running",
            )
            await self.state.create(agent_task)
            return agent_task
        except Exception as e:
            raise Exception(f"Unexpected error ocurred while managing incoming task: {e}") from e

    async def _manage_agent_response_task(
        self, agent_task: AgentTask, agent_response: TealAgentsResponse
    ) -> None:
        new_item = AgentTaskItem(
            task_id=agent_response.task_id,
            role="assistant",
            item=MultiModalItem(content_type=ContentType.TEXT, content=agent_response.output),
            request_id=agent_response.request_id,
            updated=datetime.now(),
        )
        agent_task.items.append(new_item)
        agent_task.last_updated = datetime.now()
        await self.state.update(agent_task)

    @staticmethod
    def _validate_user_id(user_id: str, task_id: str, agent_task: AgentTask) -> None:
        try:
            assert user_id == agent_task.user_id
        except AssertionError as e:
            raise AgentInvokeException(
                message=f"Invalid user ID {user_id} and task ID {task_id} provided. {e}"
            ) from e

    @staticmethod
    def _build_chat_history(agent_task: AgentTask, chat_history: ChatHistory) -> ChatHistory:
        chat_message_items: list[TextContent | ImageContent] = []
        for task_item in agent_task.items:
            chat_message_items.append(item_to_content(task_item.item))
            message_content = ChatMessageContent(role=task_item.role, items=chat_message_items)
            chat_history.add_message(message_content)
        return chat_history

    @staticmethod
    def _rejected_task_item(task_id:str, request_id:str) -> AgentTaskItem:
        return AgentTaskItem(
            task_id=task_id,
            role="assistant",
            item=MultiModalItem(
                content_type=ContentType.TEXT,
                content="tool execution rejected by user"
            ),
            request_id=request_id,
            updated=datetime.now()
        )
    
    async def resume_task(self, auth_token: str, request_id: str, action_status: dict[str,str], stream: bool
    ) -> TealAgentsResponse | RejectedToolResponse:
        user_id = self.authenticate_user(token=auth_token)
        agent_task:AgentTask = await self.state.load_by_request_id(request_id)
        session_id = agent_task.session_id
        task_id = agent_task.task_id



        TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)
        assert agent_task.status == "Paused"
        
        if action_status.get("action") == "reject":
            agent_task.status = "Canceled"
            agent_task.items.append(
                TealAgentsV1Alpha1Handler._rejected_task_item(
                    task_id=agent_task.task_id,
                    request_id=request_id
                )
            )
            await self.state.update(agent_task)
            return RejectedToolResponse(
                task_id=agent_task.task_id,
                session_id=agent_task.session_id,
                request_id=request_id
            )
        
        # Retrieve the pending_tool_calls from the last AgentTaskItem ---> What instance type comes from pending tool calls?
        _pending_tools = [fc for fc in agent_task.items[-1].pending_tool_calls] ## Needs to deserialize it 
        pending_tools = [
            FunctionCallContent(
                function_name=function_call["function_name"],
                plugin_name=function_call["plugin_name"],
                arguments=function_call["arguments"]
            )
            for function_call in _pending_tools
            ]
        # Execute the tool calls using asyncio.gather(), just as the agent would have.
        # Re-build the agent based on the existing state. 
        extra_data_collector = ExtraDataCollector()
        agent = self.agent_builder.build_agent(self.config.get_agent(), extra_data_collector)
        chat_history = ChatHistory()
        TealAgentsV1Alpha1Handler._build_chat_history(agent_task, chat_history) 
        kernel = agent.agent.kernel

        # Create ToolContent objects from the results.... _invoking_function will return FunctionResultContent
        results = await asyncio.gather(
                    *[self._invoke_function(kernel, fc) for fc in pending_tools]
                )
        
        # Add the AgentTaskItem with the pending_tool_calls and a new AgentTaskItem with the ToolContent results to the chat history.
        for result in results:
            chat_history.add_message(result.to_chat_message_content()) ## ChatMessageContent.role == tool, items=FunctionCallContent

        
        agent_task.items.append(
            AgentTaskItem(
                task_id=agent_task.task_id,
                role="assistant",
                item=MultiModalItem(
                    content_type=ContentType.TEXT,
                    content="Tool call output" ## 
                )
            )
        )
        
        # Update the AgentTask.status to "Running".
        agent_task.status = "Running"
        self.state.update(agent_task)
        
        # Invoke the agent again with the updated chat history to get the final response from the LLM.
        # Use .invoke or invoke_stream method.
        user_message = UserMessage(
            session_id=agent_task.sesion_id,
            task_id=agent_task.task_id,
            items=agent_task.items,
            #user_context=??????????
        )
        if stream:
            final_response_stream = self.invoke_stream(auth_token=auth_token, inputs=user_message)
            return final_response_stream

        final_response_invoke = self.invoke(auth_token=auth_token, inputs=user_message)
        return final_response_invoke
        # Return the final TealAgentsResponse to the client.

    async def invoke(
        self, auth_token: str, inputs: UserMessage | None = None
    ) -> TealAgentsResponse | HitlResponse:
        # Initial setup
        user_id = self.authenticate_user(token=auth_token)
        session_id, task_id, request_id = TealAgentsV1Alpha1Handler.handle_state_id(inputs)
        agent_task = await self._manage_incoming_task(
            task_id, session_id, user_id, request_id, inputs
        )
        # Check user_id match request and state
        TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)

        # Build agent and chat history
        extra_data_collector = ExtraDataCollector()
        agent = self.agent_builder.build_agent(self.config.get_agent(), extra_data_collector)
        chat_history = ChatHistory()
        TealAgentsV1Alpha1Handler._augment_with_user_context(
            inputs=inputs, chat_history=chat_history
        )
        TealAgentsV1Alpha1Handler._build_chat_history(agent_task, chat_history)

        # Prepare metadata
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0

        try:
            # Manual tool calling implementation (existing logic)
            kernel = agent.agent.kernel
            arguments = agent.agent.arguments
            chat_completion_service, settings = kernel.select_ai_service(
                arguments=arguments, type=ChatCompletionClientBase
            )
            assert isinstance(chat_completion_service, ChatCompletionClientBase)

            # Initial call to the LLM
            response_list = []
            async for response_chunk in chat_completion_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=settings,
                kernel=kernel,
                arguments=arguments,
            ):
                response_list.extend(response_chunk)

            function_calls = []
            final_response = None

            # Separate content and tool calls
            for response in response_list:
                # Update token usage
                call_usage = get_token_usage_for_response(agent.get_model_type(), response)
                completion_tokens += call_usage.completion_tokens
                prompt_tokens += call_usage.prompt_tokens
                total_tokens += call_usage.total_tokens

                # A response may have multiple items, e.g., multiple tool calls
                fc_in_response = [
                    item for item in response.items if isinstance(item, FunctionCallContent)
                ]

                if fc_in_response:
                    chat_history.add_message(response)  # Add assistant's message to history
                    function_calls.extend(fc_in_response)
                else:
                    # If no function calls, it's a direct answer
                    final_response = response

            # If tool calls were returned, execute them
            if function_calls:
                # --- INTERCEPTION POINT ---
                intervention_calls = []
                non_intervention_calls = []

                for fc in function_calls:
                    if hitl_manager.check_for_intervention(fc):
                        intervention_calls.append(fc)
                    else:
                        non_intervention_calls.append(fc)

                # Process non-intervention function calls first
                if non_intervention_calls:
                    results = await asyncio.gather(
                        *[self._invoke_function(kernel, fc) for fc in non_intervention_calls]
                    )

                    # Add results to history
                    for result in results:
                        chat_history.add_message(result.to_chat_message_content())

                # Handle intervention function calls
                if intervention_calls:
                    logger.info(
                        f"Intervention required for {len(intervention_calls)} function calls.")
                    raise hitl_manager.HitlInterventionRequired(intervention_calls)

                # Make a recursive call to get the final response from the LLM
                recursive_response = await self.invoke(auth_token, inputs)
                return recursive_response

            # No tool calls, return the direct response
            if final_response is None:
                logger.exception("No response received from LLM")
                raise AgentInvokeException("No response received from LLM")

        except hitl_manager.HitlInterventionRequired as hitl_exc:
            # --- HITL HANDLING ---
            agent_task.status = "Paused"
            assistant_item = AgentTaskItem(
                task_id=task_id,
                role="assistant",
                item=MultiModalItem(
                    content_type=ContentType.TEXT, content="HITL intervention required."),
                request_id=request_id,
                updated=datetime.now(),
                pending_tool_calls=[fc.model_dump() for fc in hitl_exc.function_calls],
            )
            agent_task.items.append(assistant_item)
            agent_task.last_updated = datetime.now()
            await self.state.update(agent_task)

            base_url = "/tealagents/v1alpha1/resume"
            approval_url = f"{base_url}/{request_id}?action=approve"
            rejection_url = f"{base_url}/{request_id}?action=reject"

            hitl_response = HitlResponse(
                session_id=session_id,
                task_id=task_id,
                request_id=request_id,
                tool_calls=[fc.model_dump() for fc in hitl_exc.function_calls],
                approval_url=approval_url,
                rejection_url=rejection_url,
            )
            return hitl_response

        except Exception as e:
            logger.exception(
                f"Error invoking {self.name}:{self.version}"
                f"for Session ID {session_id}, Task ID {task_id}, Request ID {request_id}, "
                f"Error message: {str(e)}",
                exc_info=True,
            )
            raise AgentInvokeException(
                f"Error invoking {self.name}:{self.version}"
                f"for Session ID {session_id}, Task ID {task_id}, Request ID {request_id}, "
                f"Error message: {str(e)}"
            ) from e

        # Persist and return response
        agent_response = TealAgentsResponse(
            session_id=session_id,
            task_id=task_id,
            request_id=request_id,
            output=final_response.content,
            source=f"{self.name}:{self.version}",
            token_usage=TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            ),
            extra_data=extra_data_collector.get_extra_data(),
        )
        await self._manage_agent_response_task(agent_task, agent_response)
        logger.info(
            f"{self.name}:{self.version} successful invocation with {total_tokens} tokens. "
            f"Session ID: {session_id}, Task ID: {task_id}, Request ID {request_id}"
        )

        return agent_response

    async def invoke_stream(
        self, auth_token: str, inputs: UserMessage | None = None
    ) -> AsyncIterable[TealAgentsResponse | TealAgentsPartialResponse]:
        # Initial setup
        user_id = self.authenticate_user(token=auth_token)
        session_id, task_id, request_id = TealAgentsV1Alpha1Handler.handle_state_id(inputs)
        agent_task = await self._manage_incoming_task(
            task_id, session_id, user_id, request_id, inputs
        )
        # Check user_id match request and state
        TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)

        # Build agent and chat history
        extra_data_collector = ExtraDataCollector()
        agent = self.agent_builder.build_agent(self.config.get_agent(), extra_data_collector)
        chat_history = ChatHistory()
        TealAgentsV1Alpha1Handler._augment_with_user_context(
            inputs=inputs, chat_history=chat_history
        )
        TealAgentsV1Alpha1Handler._build_chat_history(agent_task, chat_history)

        # Prepare response and metadata
        final_response = []
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0

        try:
            kernel = agent.agent.kernel
            arguments = agent.agent.arguments
            chat_completion_service, settings = kernel.select_ai_service(
                arguments=arguments, type=ChatCompletionClientBase
            )
            assert isinstance(chat_completion_service, ChatCompletionClientBase)

            all_responses = []
            # Stream the initial response from the LLM
            async for response_list in chat_completion_service.get_streaming_chat_message_contents(
                chat_history=chat_history,
                settings=settings,
                kernel=kernel,
                arguments=arguments,
            ):
                for response in response_list:
                    all_responses.append(response)
                    # Calculate usage metrics
                    call_usage = get_token_usage_for_response(agent.get_model_type(), response)
                    completion_tokens += call_usage.completion_tokens
                    prompt_tokens += call_usage.prompt_tokens
                    total_tokens += call_usage.total_tokens

                    if response.content:
                        try:
                            # Attempt to parse as ExtraDataPartial
                            extra_data_partial: ExtraDataPartial = ExtraDataPartial.new_from_json(
                                response.content
                            )
                            extra_data_collector.add_extra_data_items(extra_data_partial.extra_data)
                        except Exception:
                            if len(response.content) > 0:
                                # Handle and return partial response
                                final_response.append(response.content)
                                yield TealAgentsPartialResponse(
                                    session_id=session_id,
                                    task_id=task_id,
                                    request_id=request_id,
                                    output_partial=response.content,
                                    source=f"{self.name}:{self.version}",
                                )

            # Aggregate the full response to check for tool calls
            if not all_responses:
                return

            full_completion: StreamingChatMessageContent = reduce(lambda x, y: x + y, all_responses)
            function_calls = [
                item for item in full_completion.items if isinstance(item, FunctionCallContent)
            ]

            # If tool calls are present, execute them
            if function_calls:
                chat_history.add_message(full_completion.to_chat_message_content())

                # --- INTERCEPTION POINT ---
                intervention_calls = []
                non_intervention_calls = []

                # Separate function calls into intervention and non-intervention
                for fc in function_calls:
                    if hitl_manager.check_for_intervention(fc):
                        intervention_calls.append(fc)
                    else:
                        non_intervention_calls.append(fc)

                # Process non-intervention function calls first
                if non_intervention_calls:
                    results = await asyncio.gather(
                        *[self._invoke_function(kernel, fc) for fc in non_intervention_calls]
                    )

                    # Add results to history
                    for result in results:
                        chat_history.add_message(result.to_chat_message_content())

                # Handle intervention function calls
                if intervention_calls:
                    logger.info(
                        f"Intervention required for {len(intervention_calls)} function calls."
                    )
                    raise hitl_manager.HitlInterventionRequired(intervention_calls)

                # Make a recursive call to get the final streamed response
                async for final_response_chunk in self.invoke_stream(auth_token, inputs):
                    yield final_response_chunk
                return

        except hitl_manager.HitlInterventionRequired as hitl_exc:
            # --- HITL HANDLING ---
            agent_task.status = "Paused"
            assistant_item = AgentTaskItem(
                task_id=task_id,
                role="assistant",
                item=MultiModalItem(
                    content_type=ContentType.TEXT, content="HITL intervention required."
                ),
                request_id=request_id,
                updated=datetime.now(),
                pending_tool_calls=[fc.model_dump() for fc in hitl_exc.function_calls],
            )
            agent_task.items.append(assistant_item)
            agent_task.last_updated = datetime.now()
            await self.state.update(agent_task)

            base_url = "/tealagents/v1alpha1/resume"
            approval_url = f"{base_url}/{request_id}?action=approve"
            rejection_url = f"{base_url}/{request_id}?action=reject"

            hitl_response = HitlResponse(
                session_id=session_id,
                task_id=task_id,
                request_id=request_id,
                tool_calls=[fc.model_dump() for fc in hitl_exc.function_calls],
                approval_url=approval_url,
                rejection_url=rejection_url,
            )
            yield hitl_response
            return

        except Exception as e:
            logger.exception(
                f"Error invoking stream for {self.name}:{self.version} "
                f"for Session ID {session_id}, Task ID {task_id}, Request ID {request_id}. "
                f"Error message: {str(e)}",
                exc_info=True,
            )
            raise AgentInvokeException(
                f"Error invoking stream for {self.name}:{self.version}"
                f" for Session ID {session_id}, Task ID {task_id}, Request ID {request_id}, "
                f"Error message: {str(e)}"
            ) from e

        # Persist and return response
        final_response_text = "".join(final_response)
        agent_response = TealAgentsResponse(
            session_id=session_id,
            task_id=task_id,
            request_id=request_id,
            output=final_response_text,
            source=f"{self.name}:{self.version}",
            token_usage=TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            ),
            extra_data=extra_data_collector.get_extra_data(),
        )
        await self._manage_agent_response_task(agent_task, agent_response)
        logger.info(
            f"Agent successful stream invocation. "
            f"Session ID: {session_id}, Task ID: {task_id}, Request ID {request_id}"
        )
        yield agent_response
