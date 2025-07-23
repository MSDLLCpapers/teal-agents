import logging
import uuid
from collections.abc import AsyncIterable
from datetime import datetime

from semantic_kernel.contents import ChatMessageContent, ImageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.utils.author_role import AuthorRole

from sk_agents.authorization.dummy_authorizer import DummyAuthorizer
from sk_agents.exceptions import AgentInvokeException, AuthenticationException, PersistenceLoadError
from sk_agents.extra_data_collector import ExtraDataCollector, ExtraDataPartial
from sk_agents.persistence.in_memory_persistence_manager import InMemoryPersistenceManager
from sk_agents.ska_types import BaseConfig, BaseHandler, ContentType, TokenUsage
from sk_agents.tealagents.models import (
    AgentTask,
    AgentTaskItem,
    MultiModalItem,
    TealAgentsPartialResponse,
    TealAgentsResponse,
    UserMessage,
)
from sk_agents.tealagents.v1alpha1.agent.config import Config
from sk_agents.tealagents.v1alpha1.agent_builder import AgentBuilder
from sk_agents.tealagents.v1alpha1.utils import get_token_usage_for_response, item_to_content

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

    async def invoke(
        self, auth_token: str, inputs: UserMessage | None = None
    ) -> TealAgentsResponse:
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
        response_content = []
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0

        # Invoke the agent
        try:
            async for content in agent.invoke(chat_history):
                response_content.append(content)
                call_usage = get_token_usage_for_response(agent.get_model_type(), content)
                completion_tokens += call_usage.completion_tokens
                prompt_tokens += call_usage.prompt_tokens
                total_tokens += call_usage.total_tokens
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
            output=response_content[-1].content,
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

        # Process the final task with streaming
        try:
            async for chunk in agent.invoke_stream(chat_history):
                # Initialize content as the partial message in chunk
                content = chunk.content
                # Calculate usage metrics
                call_usage = get_token_usage_for_response(agent.get_model_type(), chunk)
                completion_tokens += call_usage.completion_tokens
                prompt_tokens += call_usage.prompt_tokens
                total_tokens += call_usage.total_tokens
                try:
                    # Attempt to parse as ExtraDataPartial
                    extra_data_partial: ExtraDataPartial = ExtraDataPartial.new_from_json(content)
                    extra_data_collector.add_extra_data_items(extra_data_partial.extra_data)
                except Exception:
                    if len(content) > 0:
                        # Handle and return partial response
                        final_response.append(content)
                        yield TealAgentsPartialResponse(
                            session_id=session_id,
                            task_id=task_id,
                            request_id=request_id,
                            output_partial=content,
                            source=f"{self.name}:{self.version}",
                        )
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
        final_response = "".join(final_response)
        agent_response = TealAgentsResponse(
            session_id=session_id,
            task_id=task_id,
            request_id=request_id,
            output=final_response,
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
