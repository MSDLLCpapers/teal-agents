import asyncio
import logging
import uuid
from collections.abc import AsyncIterable
from datetime import datetime
from functools import reduce
from typing import Literal

from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.contents import ChatMessageContent, ImageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.function_result_content import FunctionResultContent
from semantic_kernel.contents.streaming_chat_message_content import StreamingChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole
from semantic_kernel.kernel import Kernel
from ska_utils import AppConfig

from sk_agents.authorization.dummy_authorizer import DummyAuthorizer
from sk_agents.exceptions import (
    AgentInvokeException,
    AuthenticationException,
    PersistenceCreateError,
    PersistenceLoadError,
)
from sk_agents.extra_data_collector import ExtraDataCollector, ExtraDataPartial
from sk_agents.hitl import hitl_manager
from sk_agents.persistence.task_persistence_manager import TaskPersistenceManager
from sk_agents.ska_types import BaseConfig, BaseHandler, ContentType, TokenUsage
from sk_agents.tealagents.models import (
    AgentTask,
    AgentTaskItem,
    AuthChallengeResponse,
    HitlResponse,
    MultiModalItem,
    RejectedToolResponse,
    ResumeRequest,
    TealAgentsPartialResponse,
    TealAgentsResponse,
    UserMessage,
)
from sk_agents.tealagents.v1alpha1.agent.config import Config
from sk_agents.tealagents.v1alpha1.agent_builder import AgentBuilder
from sk_agents.tealagents.v1alpha1.utils import get_token_usage_for_response, item_to_content
from sk_agents.mcp_client import ElicitationResponse
from sk_agents.mcp_elicitation_models import McpElicitationRequired

logger = logging.getLogger(__name__)

class TealAgentsV1Alpha1Handler(BaseHandler):
    def __init__(
        self,
        config: BaseConfig,
        app_config: AppConfig,
        agent_builder: AgentBuilder,
        state_manager: TaskPersistenceManager,
        discovery_manager=None,  # McpStateManager - Optional, only needed for MCP
    ):
        self.version = config.version
        self.name = config.name
        self.app_config = app_config
        if hasattr(config, "spec"):
            self.config = Config(config=config)
        else:
            raise ValueError("Invalid config")
        self.agent_builder = agent_builder
        self.state = state_manager
        self.authorizer = DummyAuthorizer()
        self.discovery_manager = discovery_manager  # Store discovery manager (optional)

        # Track which sessions have seen MCP auth status messages (to show only once per session)
        self._mcp_status_shown_per_session: set[str] = set()

    def _get_elicitation_modes(self) -> dict | None:
        """
        Determine which elicitation modes to advertise based on config.

        Returns a dict like {"form": {}, "url": {}} or None to disable capability.
        """
        cfg = getattr(self.config.get_agent(), "elicitation", None)
        enable_form = True
        enable_url = True
        if cfg:
            enable_form = bool(getattr(cfg, "enable_form", True))
            enable_url = bool(getattr(cfg, "enable_url", True))

        modes = {}
        if enable_form:
            modes["form"] = {}
        if enable_url:
            modes["url"] = {}

        return modes if modes else None

    @staticmethod
    async def _default_elicitation_handler(req):
        """
        Default handler: reject politely so server can continue gracefully.
        Users can override by wiring a real handler.
        """
        return ElicitationResponse(action="reject", content=None)

    async def _ensure_session_discovery(
        self, user_id: str, session_id: str, task_id: str, request_id: str
    ) -> AuthChallengeResponse | None:
        """
        Ensure MCP tool discovery has been performed for this session.

        Discovery happens once per (user_id, session_id) when first detected.
        All tasks in the session share the discovered tools.

        Args:
            user_id: User ID for authentication
            session_id: Session ID for session-level scoping
            task_id: Task ID for auth challenge response
            request_id: Request ID for auth challenge response

        Returns:
            AuthChallengeResponse if authentication is required, None if discovery complete
        """
        # Early return if no discovery manager (no MCP servers configured)
        if not self.discovery_manager:
            return None

        # Check if discovery already completed for this session
        is_completed = await self.discovery_manager.is_completed(user_id, session_id)
        if is_completed:
            logger.debug(
                f"MCP discovery already completed for session: {session_id}"
            )
            return None

        # Load or create discovery state
        discovery_state = await self.discovery_manager.load_discovery(user_id, session_id)
        if not discovery_state:
            from sk_agents.mcp_discovery.mcp_discovery_manager import McpState

            discovery_state = McpState(
                user_id=user_id,
                session_id=session_id,
                discovered_servers={},
                discovery_completed=False,
            )
            await self.discovery_manager.create_discovery(discovery_state)
            logger.info(f"Created discovery state for session: {session_id}")

        # Check if MCP servers configured
        mcp_servers = self.config.get_agent().mcp_servers
        if not mcp_servers or len(mcp_servers) == 0:
            await self.discovery_manager.mark_completed(user_id, session_id)
            return None

        try:
            from sk_agents.mcp_client import AuthRequiredError
            from sk_agents.mcp_plugin_registry import McpPluginRegistry

            logger.info(
                f"Starting MCP discovery for session {session_id} ({len(mcp_servers)} servers)"
            )

            await McpPluginRegistry.discover_and_materialize(
                mcp_servers, user_id, session_id, self.discovery_manager, self.app_config
            )

            await self.discovery_manager.mark_completed(user_id, session_id)
            logger.info(f"MCP discovery completed for session {session_id}")
            return None

        except AuthRequiredError as e:
            # Auth required - return challenge
            logger.info(
                f"MCP discovery requires authentication for '{e.server_name}' "
                f"(session: {session_id})"
            )

            try:
                # Find server config
                server_config = next(
                    (s for s in mcp_servers if s.name == e.server_name), None
                )
                if not server_config:
                    raise ValueError(f"Server config not found for '{e.server_name}'")

                # Initiate OAuth 2.1 authorization flow with PKCE
                from sk_agents.auth.oauth_client import OAuthClient

                oauth_client = OAuthClient()

                # Generate authorization URL with PKCE
                auth_url = await oauth_client.initiate_authorization_flow(
                    server_config=server_config, user_id=user_id
                )

                logger.info(f"Generated OAuth authorization URL for {e.server_name}")

                return AuthChallengeResponse(
                    task_id=task_id,
                    session_id=session_id,
                    request_id=request_id,
                    message=f"Authentication required for MCP server '{e.server_name}'.",
                    auth_challenges=[
                        {
                            "server_name": e.server_name,
                            "auth_server": e.auth_server,
                            "scopes": e.scopes,
                            "auth_url": auth_url,
                        }
                    ],
                    resume_url=f"/tealagents/v1alpha1/invoke",
                )

            except Exception as oauth_error:
                logger.error(f"Failed to initiate OAuth flow: {oauth_error}")
                return AuthChallengeResponse(
                    task_id=task_id,
                    session_id=session_id,
                    request_id=request_id,
                    message=f"Authentication required for MCP server '{e.server_name}'.",
                    auth_challenges=[
                        {
                            "server_name": e.server_name,
                            "auth_server": e.auth_server,
                            "scopes": e.scopes,
                            "auth_url": f"{e.auth_server}/authorize?error=oauth_client_failed",
                        }
                    ],
                    resume_url=f"/tealagents/v1alpha1/invoke",
                )

        except Exception as e:
            logger.error(f"MCP discovery failed for session {session_id}: {e}")
            raise

    @staticmethod
    async def _invoke_function(
        kernel: Kernel, fc_content: FunctionCallContent
    ) -> FunctionResultContent:
        """Helper to execute a single tool function call."""
        function = kernel.get_function(
            fc_content.plugin_name,
            fc_content.function_name,
        )
        kernel_argument = fc_content.to_kernel_arguments()
        function_result = await function.invoke(kernel, kernel_argument)
        return FunctionResultContent.from_function_call_content_and_result(
            fc_content, function_result
        )

    @staticmethod
    def _augment_with_user_context(inputs: UserMessage, chat_history: ChatHistory) -> None:
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
        role: Literal["user", "assistant"],
        request_id: str,
        inputs: UserMessage,
        status: Literal["Running", "Paused", "Completed", "Failed", "Canceled"],
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

    async def authenticate_user(self, token: str) -> str:
        try:
            user_id = await self.authorizer.authorize_request(auth_header=token)
            return user_id
        except Exception as e:
            raise AuthenticationException(
                message=(f"Unable to authenticate user, exception message: {e}")
            ) from e

    async def authenticate_mcp_servers(self, user_id: str, session_id: str, task_id: str, request_id: str) -> AuthChallengeResponse | None:
        """
        Authenticate MCP servers before agent construction.

        Returns AuthChallengeResponse if authentication is needed, None if all servers are authenticated.
        """
        mcp_servers = self.config.get_agent().mcp_servers
        if not mcp_servers:
            return None

        try:
            from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
            from sk_agents.mcp_client import build_auth_storage_key

            auth_storage_factory = AuthStorageFactory(self.app_config)
            auth_storage = auth_storage_factory.get_auth_storage_manager()

            missing_auth_servers = []

            for server_config in mcp_servers:
                if server_config.auth_server and server_config.scopes:
                    # Check if we have valid auth for this server
                    composite_key = build_auth_storage_key(
                        server_config.auth_server,
                        server_config.scopes
                    )
                    auth_data = auth_storage.retrieve(user_id, composite_key)

                    if not auth_data:
                        # Missing authentication for this server
                        auth_challenge = {
                            "server_name": server_config.name,
                            "auth_server": server_config.auth_server,
                            "scopes": server_config.scopes,
                            "auth_url": f"{server_config.auth_server}/authorize?client_id=teal_agents&scope={'%20'.join(server_config.scopes)}&response_type=code"
                        }
                        missing_auth_servers.append(auth_challenge)

            if missing_auth_servers:
                return AuthChallengeResponse(
                    task_id=task_id,
                    session_id=session_id,
                    request_id=request_id,
                    message=f"Authentication required for {len(missing_auth_servers)} MCP server(s).",
                    auth_challenges=missing_auth_servers,
                    resume_url=f"/tealagents/v1alpha1/resume/{request_id}"
                )

            return None

        except Exception as e:
            logger.warning(f"Error during MCP server authentication check: {e}")
            # Continue without MCP auth if there are issues with auth storage
            return None

    @staticmethod
    def handle_state_id(inputs: UserMessage) -> tuple[str, str, str]:
        if inputs.session_id:
            session_id = inputs.session_id
        else:
            session_id = str(uuid.uuid4())

        if inputs.task_id:
            task_id = inputs.task_id
        else:
            task_id = str(uuid.uuid4())

        request_id = str(uuid.uuid4())

        return session_id, task_id, request_id

    async def _manage_incoming_task(
        self, task_id: str, session_id: str, user_id: str, request_id: str, inputs: UserMessage
    ) -> AgentTask | None:
        try:
            agent_task = await self.state.load(task_id)
            if not agent_task:
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
        except (PersistenceLoadError, PersistenceCreateError) as e:
            raise AgentInvokeException(
                f"Failed to load or create task {task_id}: {e.message}"
            ) from e
        except Exception as e:
            raise AgentInvokeException(
                f"Unexpected error occurred while managing incoming task {task_id}: {str(e)}"
            ) from e

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
                message=(f"Invalid user ID {user_id}and task ID {task_id} provided. {e}")
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
    def _rejected_task_item(task_id: str, request_id: str) -> AgentTaskItem:
        return AgentTaskItem(
            task_id=task_id,
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="tool execution rejected"),
            request_id=request_id,
            updated=datetime.now(),
        )

    @staticmethod
    def _approved_task_item(task_id: str, request_id: str) -> AgentTaskItem:
        return AgentTaskItem(
            task_id=task_id,
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="tool execution approved"),
            request_id=request_id,
            updated=datetime.now(),
        )

    async def _manage_hitl_exception(
        self,
        agent_task: AgentTask,
        session_id: str,
        task_id: str,
        request_id: str,
        function_calls: list,
        chat_history: ChatHistory,
    ):
        agent_task.status = "Paused"
        assistant_item = AgentTaskItem(
            task_id=task_id,
            role="assistant",
            item=MultiModalItem(
                content_type=ContentType.TEXT, content="HITL intervention required."
            ),
            request_id=request_id,
            updated=datetime.now(),
            pending_tool_calls=[fc.model_dump() for fc in function_calls],
            chat_history=chat_history,
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
            tool_calls=[fc.model_dump() for fc in function_calls],
            approval_url=approval_url,
            rejection_url=rejection_url,
        )
        return hitl_response

    @staticmethod
    async def _manage_function_calls(
        function_calls: list[FunctionCallContent], chat_history: ChatHistory, kernel: Kernel
    ) -> None:
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
                *[
                    TealAgentsV1Alpha1Handler._invoke_function(kernel, fc)
                    for fc in non_intervention_calls
                ]
            )

            # Add results to history
            for result in results:
                chat_history.add_message(result.to_chat_message_content())

        # Handle intervention function calls
        if intervention_calls:
            logger.info(f"Intervention required for{len(intervention_calls)} function calls.")
            raise hitl_manager.HitlInterventionRequired(intervention_calls)

    async def prepare_agent_response(
        self,
        agent_task: AgentTask,
        request_id: str,
        response: ChatMessageContent | list[str],
        token_usage: TokenUsage,
        extra_data_collector: ExtraDataCollector,
    ):
        if isinstance(response, list):
            agent_output = "".join(response)
        else:
            agent_output = response.content

        total_tokens = token_usage.total_tokens
        session_id = agent_task.session_id
        task_id = agent_task.task_id
        request_id = request_id

        agent_response = TealAgentsResponse(
            session_id=session_id,
            task_id=task_id,
            request_id=request_id,
            output=agent_output,
            source=f"{self.name}:{self.version}",
            token_usage=token_usage,
            extra_data=extra_data_collector.get_extra_data(),
        )
        await self._manage_agent_response_task(agent_task, agent_response)
        logger.info(
            f"{self.name}:{self.version}"
            f"successful invocation with {total_tokens} tokens. "
            f"Session ID: {session_id}, Task ID: {task_id},"
            f"Request ID {request_id}"
        )
        return agent_response

    async def resume_task(
        self, auth_token: str, request_id: str, action_status: ResumeRequest, stream: bool
    ) -> (
        TealAgentsResponse
        | RejectedToolResponse
        | HitlResponse
        | AsyncIterable[TealAgentsResponse | TealAgentsPartialResponse | HitlResponse]
    ):
        user_id = await self.authenticate_user(token=auth_token)
        agent_task = await self.state.load_by_request_id(request_id)
        if agent_task is None:
            raise AgentInvokeException(f"No agent task found for request ID: {request_id}")

        # Validate task has items
        if not agent_task.items:
            raise AgentInvokeException(
                f"Cannot resume task {request_id}: task has no items. "
                f"Task may be corrupted or improperly initialized."
            )

        session_id = agent_task.session_id
        task_id = agent_task.task_id

        # Retrieve chat history from last item with validation
        last_item = agent_task.items[-1]
        if last_item.chat_history is None:
            raise AgentInvokeException(
                f"Cannot resume task {request_id}: chat history not preserved in paused state. "
                f"This indicates a persistence layer issue during HITL pause."
            )
        chat_history = last_item.chat_history

        TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)

        # Validate task is in correct state for resumption
        if agent_task.status != "Paused":
            raise AgentInvokeException(
                f"Cannot resume task {task_id}: task is in '{agent_task.status}' state, "
                f"expected 'Paused'. Task may have already been processed or cancelled."
            )

        if action_status.action != "approve":
            agent_task.status = "Canceled"
            agent_task.items.append(
                TealAgentsV1Alpha1Handler._rejected_task_item(
                    task_id=task_id, request_id=request_id
                )
            )
            agent_task.last_updated = datetime.now()
            await self.state.update(agent_task)

            return RejectedToolResponse(
                task_id=task_id, session_id=agent_task.session_id, request_id=request_id
            )
        # Record Approval state
        agent_task.status = "Running"
        agent_task.items.append(
            TealAgentsV1Alpha1Handler._approved_task_item(
                task_id=agent_task.task_id, request_id=request_id
            )
        )
        agent_task.last_updated = datetime.now()
        await self.state.update(agent_task)

        # Retrieve the pending_tool_calls from the last AgentTaskItem before approval/rejection item
        # Validate sufficient items exist
        if len(agent_task.items) < 2:
            raise AgentInvokeException(
                f"Invalid task state for request ID {request_id}: "
                f"expected at least 2 task items for HITL resume, found {len(agent_task.items)}"
            )

        pending_tools_item = agent_task.items[-2]
        if not pending_tools_item.pending_tool_calls:
            raise AgentInvokeException(
                f"Pending tool calls not found for request ID: {request_id}. "
                f"Task item at index -2 has no pending tool calls."
            )

        _pending_tools = list(pending_tools_item.pending_tool_calls)
        pending_tools = [FunctionCallContent(**function_call) for function_call in _pending_tools]

        # Execute the tool calls using asyncio.gather(),
        # just as the agent would have.
        extra_data_collector = ExtraDataCollector()
        agent = self.agent_builder.build_agent(self.config.get_agent(), extra_data_collector, user_id=user_id)

        # Load MCP plugins after agent construction (per-session isolation)
        if self.config.get_agent().mcp_servers and self.discovery_manager:
            await self.agent_builder.kernel_builder.load_mcp_plugins(
                agent.agent.kernel,
                user_id,
                session_id,
                self.discovery_manager,
                elicitation_handler=None,
                elicitation_modes=self._get_elicitation_modes(),
            )

        kernel = agent.agent.kernel

        # Create ToolContent objects from the results
        results = await asyncio.gather(
            *[TealAgentsV1Alpha1Handler._invoke_function(kernel, fc) for fc in pending_tools]
        )
        # Add results to chat history
        for result in results:
            chat_history.add_message(result.to_chat_message_content())

        if stream:
            final_response_stream = self.recursion_invoke_stream(
                chat_history, session_id, task_id, request_id
            )
            return final_response_stream
        else:
            final_response_invoke = await self.recursion_invoke(
                inputs=chat_history, session_id=session_id, request_id=request_id, task_id=task_id
            )

            return final_response_invoke

    async def invoke(
        self, auth_token: str, inputs: UserMessage
    ) -> TealAgentsResponse | HitlResponse | AuthChallengeResponse:
        # Initial setup
        logger.info("Beginning processing invoke")

        user_id = await self.authenticate_user(token=auth_token)

        # Generate state IDs first (needed for auth challenges)
        state_ids = TealAgentsV1Alpha1Handler.handle_state_id(inputs)
        session_id, task_id, request_id = state_ids
        inputs.session_id = session_id
        inputs.task_id = task_id

        # Ensure MCP discovery has been performed for this session
        # May return AuthChallengeResponse if auth required during discovery
        discovery_auth_challenge = await self._ensure_session_discovery(
            user_id, session_id, task_id, request_id
        )
        if discovery_auth_challenge:
            logger.info("Returning auth challenge from MCP discovery")
            return discovery_auth_challenge

        agent_task = await self._manage_incoming_task(
            task_id, session_id, user_id, request_id, inputs
        )
        if agent_task is None:
            raise AgentInvokeException("Agent task not created")
        # Check user_id match request and state
        TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)

        # Check MCP server authentication before agent construction
        auth_challenge = await self.authenticate_mcp_servers(user_id, session_id, task_id, request_id)
        if auth_challenge:
            logger.info(f"MCP authentication required for {len(auth_challenge.auth_challenges)} server(s)")
            return auth_challenge

        chat_history = ChatHistory()
        TealAgentsV1Alpha1Handler._augment_with_user_context(
            inputs=inputs, chat_history=chat_history
        )
        TealAgentsV1Alpha1Handler._build_chat_history(agent_task, chat_history)
        logger.info("Building the final response")
        final_response_invoke = await self.recursion_invoke(
            inputs=chat_history, session_id=session_id, request_id=request_id, task_id=task_id
        )
        logger.info("Final response complete")

        return final_response_invoke

    async def invoke_stream(
        self, auth_token: str, inputs: UserMessage
    ) -> AsyncIterable[TealAgentsResponse | TealAgentsPartialResponse | HitlResponse | AuthChallengeResponse]:
        # Initial setup
        logger.info("Beginning processing invoke")
        user_id = await self.authenticate_user(token=auth_token)

        # Generate state IDs first (needed for auth challenges)
        state_ids = TealAgentsV1Alpha1Handler.handle_state_id(inputs)
        session_id, task_id, request_id = state_ids

        # Ensure MCP discovery has been performed for this session
        # May return AuthChallengeResponse if auth required during discovery
        discovery_auth_challenge = await self._ensure_session_discovery(
            user_id, session_id, task_id, request_id
        )
        if discovery_auth_challenge:
            logger.info("Returning auth challenge from MCP discovery")
            yield discovery_auth_challenge
            return

        # Notify user that MCP is ready (only once per session, after discovery)
        mcp_servers = self.config.get_agent().mcp_servers
        show_status = session_id not in self._mcp_status_shown_per_session

        if show_status and mcp_servers and len(mcp_servers) > 0:
            # Load state to check for failures
            failed_servers = {}
            if self.discovery_manager:
                try:
                    state = await self.discovery_manager.load_discovery(user_id, session_id)
                    if state:
                        failed_servers = state.failed_servers
                except Exception:
                    logger.debug("Failed to load discovery state for status message")

            all_server_names = [server.name for server in mcp_servers]
            successful_servers = [s for s in all_server_names if s not in failed_servers]
            
            messages = []
            if successful_servers:
                messages.append(f"✅ MCP connected: {', '.join(successful_servers)}")
            
            if failed_servers:
                failed_list = []
                for name, error in failed_servers.items():
                    # Truncate error if too long
                    short_error = (error[:50] + '...') if len(error) > 50 else error
                    failed_list.append(f"{name} ({short_error})")
                messages.append(f"⚠️ MCP connection failed: {', '.join(failed_list)}")
                
            status_msg = "\n".join(messages) + "\n\n"

            yield TealAgentsPartialResponse(
                task_id=task_id,
                session_id=session_id,
                request_id=request_id,
                output_partial=status_msg
            )
            # Mark this session as having seen the status message
            self._mcp_status_shown_per_session.add(session_id)

        agent_task = await self._manage_incoming_task(
            task_id, session_id, user_id, request_id, inputs
        )
        if agent_task is None:
            raise AgentInvokeException("Agent task not created")
        # Check user_id match request and state
        TealAgentsV1Alpha1Handler._validate_user_id(user_id, task_id, agent_task)

        # Check MCP server authentication before agent construction
        auth_challenge = await self.authenticate_mcp_servers(user_id, session_id, task_id, request_id)
        if auth_challenge:
            logger.info(f"MCP authentication required for {len(auth_challenge.auth_challenges)} server(s)")
            yield auth_challenge
            return

        chat_history = ChatHistory()
        TealAgentsV1Alpha1Handler._augment_with_user_context(
            inputs=inputs, chat_history=chat_history
        )
        logger.info("Building the final response")
        TealAgentsV1Alpha1Handler._build_chat_history(agent_task, chat_history)

        # Yield from the recursive stream
        async for response_chunk in self.recursion_invoke_stream(
            chat_history, session_id, task_id, request_id
        ):
            yield response_chunk

        logger.info("Final response complete")

    async def recursion_invoke(
        self, inputs: ChatHistory, session_id: str, task_id: str, request_id: str
    ) -> TealAgentsResponse | HitlResponse:
        # Initial setup

        chat_history = inputs
        agent_task = await self.state.load_by_request_id(request_id)
        if not agent_task:
            raise PersistenceLoadError(f"Agent task with ID {task_id} not found in state.")

        user_id = agent_task.user_id
        extra_data_collector = ExtraDataCollector()
        agent = await self.agent_builder.build_agent(
            self.config.get_agent(),
            extra_data_collector,
            user_id=user_id
        )

        # Load MCP plugins after agent construction (per-session isolation)
        if self.config.get_agent().mcp_servers and self.discovery_manager:
            await self.agent_builder.kernel_builder.load_mcp_plugins(
                agent.agent.kernel,
                user_id,
                session_id,
                self.discovery_manager,
                elicitation_handler=self._default_elicitation_handler,
                elicitation_modes=self._get_elicitation_modes(),
            )

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
            responses = await chat_completion_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=settings,
                kernel=kernel,
                arguments=arguments,
            )
            for response_chunk in responses:
                # response_list.extend(response_chunk)
                chat_history.add_message(response_chunk)
                response_list.append(response_chunk)

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
                    # chat_history.add_message(response)
                    # Add assistant's message to history
                    function_calls.extend(fc_in_response)
                else:
                    # If no function calls, it's a direct answer
                    final_response = response
            token_usage = TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            )
            # If tool calls were returned, execute them
            if function_calls:
                await self._manage_function_calls(function_calls, chat_history, kernel)

                # Make a recursive call to get the final response from the LLM
                recursive_response = await self.recursion_invoke(
                    inputs=chat_history,
                    session_id=session_id,
                    task_id=task_id,
                    request_id=request_id,
                )
                return recursive_response

            # No tool calls, return the direct response
            if final_response is None:
                error_msg = (
                    f"No response received from LLM for Session ID {session_id}, "
                    f"Task ID {task_id}, Request ID {request_id}. "
                    f"Function calls processed: {len(function_calls)}"
                )
                logger.error(error_msg)
                raise AgentInvokeException(error_msg)
        except hitl_manager.HitlInterventionRequired as hitl_exc:
            return await self._manage_hitl_exception(
                agent_task, session_id, task_id, request_id, hitl_exc.function_calls, chat_history
            )

        except Exception as e:
            logger.exception(
                f"Error invoking {self.name}:{self.version}"
                f"for Session ID {session_id}, Task ID {task_id},"
                f"Request ID {request_id}, Error message: {str(e)}",
                exc_info=True,
            )
            raise AgentInvokeException(
                f"Error invoking {self.name}:{self.version}"
                f"for Session ID {session_id}, Task ID {task_id},"
                f" Request ID {request_id}, Error message: {str(e)}"
            ) from e

        # Persist and return response
        return await self.prepare_agent_response(
            agent_task, request_id, final_response, token_usage, extra_data_collector
        )

    async def recursion_invoke_stream(
        self, inputs: ChatHistory, session_id: str, task_id: str, request_id: str
    ) -> AsyncIterable[TealAgentsResponse | TealAgentsPartialResponse | HitlResponse]:
        chat_history = inputs
        agent_task = await self.state.load_by_request_id(request_id)
        if not agent_task:
            raise PersistenceLoadError(f"Agent task with ID {task_id} not found in state.")

        user_id = agent_task.user_id
        extra_data_collector = ExtraDataCollector()
        agent = await self.agent_builder.build_agent(
            self.config.get_agent(),
            extra_data_collector,
            user_id=user_id
        )

        # Load MCP plugins after agent construction (per-session isolation)
        if self.config.get_agent().mcp_servers and self.discovery_manager:
            await self.agent_builder.kernel_builder.load_mcp_plugins(
                agent.agent.kernel,
                user_id,
                session_id,
                self.discovery_manager,
                elicitation_handler=self._default_elicitation_handler,
                elicitation_modes=self._get_elicitation_modes(),
            )

        # Prepare metadata
        final_response = []
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0

        try:
            kernel = agent.agent.kernel
            arguments = agent.agent.arguments
            kernel_configs = kernel.select_ai_service(
                arguments=arguments, type=ChatCompletionClientBase
            )
            chat_completion_service, settings = kernel_configs
            assert isinstance(chat_completion_service, ChatCompletionClientBase)

            all_responses = []
            # Stream the initial response from the LLM
            response_list = []
            responses = await chat_completion_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=settings,
                kernel=kernel,
                arguments=arguments,
            )
            for response_chunk in responses:
                chat_history.add_message(response_chunk)
                response_list.append(response_chunk)

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

            token_usage = TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
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
                await self._manage_function_calls(function_calls, chat_history, kernel)
                # Make a recursive call to get the final streamed response
                async for final_response_chunk in self.recursion_invoke_stream(
                    chat_history, session_id, task_id, request_id
                ):
                    yield final_response_chunk
                return
        except hitl_manager.HitlInterventionRequired as hitl_exc:
            yield await self._manage_hitl_exception(
                agent_task, session_id, task_id, request_id, hitl_exc.function_calls, chat_history
            )
            return

        except Exception as e:
            logger.exception(
                f"Error invoking stream for {self.name}:{self.version} "
                f"for Session ID {session_id}, Task ID {task_id},"
                f" Request ID {request_id}, Error message: {str(e)}",
                exc_info=True,
            )
            raise AgentInvokeException(
                f"Error invoking stream for {self.name}:{self.version}"
                f"for Session ID {session_id}, Task ID {task_id},"
                f"Request ID {request_id}, Error message: {str(e)}"
            ) from e

        # # Persist and return response
        yield await self.prepare_agent_response(
            agent_task, request_id, final_response, token_usage, extra_data_collector
        )
