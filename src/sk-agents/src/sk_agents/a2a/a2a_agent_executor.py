from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils import new_agent_text_message
from ska_utils import AppConfig

from sk_agents.a2a.request_processor import RequestProcessor
from sk_agents.a2a.response_classifier import A2AResponseClassifier
from sk_agents.ska_types import (
    BaseConfig,
    BaseHandler,
)
from sk_agents.skagents import handle as skagents_handle
from sk_agents.skagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.state.state_manager import StateManager


class A2AAgentExecutor(AgentExecutor):
    def __init__(
        self,
        config: BaseConfig,
        app_config: AppConfig,
        chat_completion_builder: ChatCompletionBuilder,
        state_manager: StateManager,
    ):
        self.config = config
        self.app_config = app_config
        self.response_classifier = A2AResponseClassifier(
            app_config=app_config, chat_completion_builder=chat_completion_builder
        )
        self.state_manager = state_manager

    async def execute(self, context: RequestContext, event_queue: EventQueue):
        try:
            handler: BaseHandler = skagents_handle(self.config, self.app_config, None)
            processor = RequestProcessor(
                handler,
                self.response_classifier,
                context,
                event_queue,
                self.state_manager,
            )
            await processor.process_request()

        except Exception as e:
            event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    contextId=context.context_id,
                    taskId=context.task_id,
                    final=True,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=new_agent_text_message(str(e)),
                    ),
                )
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue):
        await self.state_manager.set_canceled(context.task_id)

