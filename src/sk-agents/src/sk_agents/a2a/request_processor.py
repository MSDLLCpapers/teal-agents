# DEPRECATION NOTICE: A2A (Agent-to-Agent) functionality is being deprecated
# as part of the framework migration evaluation. This module is maintained for
# backward compatibility only. New development should avoid using A2A functionality.

from a2a.server.agent_execution import RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact,
    DataPart,
    FilePart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from a2a.utils import new_agent_text_message, new_data_artifact, new_text_artifact

from sk_agents.a2a.response_classifier import (
    A2AResponseClassification,
    A2AResponseClassifier,
    A2AResponseStatus,
)
from sk_agents.ska_types import (
    BaseHandler,
    BaseMultiModalInput,
    ContentType,
    HistoryMultiModalMessage,
    InvokeResponse,
    MultiModalItem,
)
from sk_agents.state.state_manager import StateManager


class RequestProcessor:
    def __init__(
        self,
        handler: BaseHandler,
        response_classifier: A2AResponseClassifier,
        context: RequestContext,
        event_queue: EventQueue,
        state_manager: StateManager,
    ):
        self.handler = handler
        self.response_classifier = response_classifier
        self.context = context
        self.event_queue = event_queue
        self.state_manager = state_manager

    @staticmethod
    def _part_to_multi_modal_item(part: Part) -> MultiModalItem:
        if isinstance(part.root, TextPart):
            return MultiModalItem(content_type=ContentType.TEXT, content=part.root.text)
        elif isinstance(part.root, DataPart):
            return MultiModalItem(content_type=ContentType.TEXT, content=str(part.root.data))
        elif isinstance(part.root, FilePart):
            return MultiModalItem(
                content_type=ContentType.IMAGE,
                content=f"data:{part.root.file.mimeType};base64,{part.root.file.data}",
            )
        else:
            raise ValueError(f"Unsupported part type: {type(part.root)}")

    @staticmethod
    def _message_to_history_multi_modal_message(
        message: Message,
    ) -> HistoryMultiModalMessage:
        return HistoryMultiModalMessage(
            role="user" if message.role == Role.user else "assistant",
            items=[RequestProcessor._part_to_multi_modal_item(part) for part in message.parts],
        )

    async def process_request(self) -> None:
        self._update_task_status(TaskState.working, status_message="Processing request...")
        new_message = self._message_to_history_multi_modal_message(self.context.message)
        all_messages = await self.state_manager.update_task_messages(
            self.context.task_id, new_message
        )
        inputs = BaseMultiModalInput(
            session_id=self.context.task_id,
            chat_history=all_messages,
        )

        response: InvokeResponse = await self.handler.invoke(inputs=inputs.__dict__)
        if await self.state_manager.is_canceled(self.context.task_id):
            self._handle_canceled()
            return
        if not response.output_raw:
            raise ValueError("Unexpected empty response from handler.")

        await self.state_manager.update_task_messages(
            self.context.task_id,
            HistoryMultiModalMessage(
                role="assistant",
                items=[MultiModalItem(content_type=ContentType.TEXT, content=response.output_raw)],
            ),
        )
        classification = await self.response_classifier.classify_response(response.output_raw)
        if await self.state_manager.is_canceled(self.context.task_id):
            self._handle_canceled()
            return

        match classification.status:
            case A2AResponseStatus.completed:
                self._handle_task_completed(response, classification)
            case A2AResponseStatus.input_required:
                self._handle_task_input_required(response, classification)
            case A2AResponseStatus.auth_required:
                self._handle_task_auth_required(response, classification)
            case A2AResponseStatus.failed:
                self._handle_task_failed(response, classification)
            case _:
                self._handle_task_unknown(response, classification)

    @staticmethod
    def _build_text_artifact(response: InvokeResponse) -> Artifact:
        return new_text_artifact("final-response", response.output_raw, "The final response")

    @staticmethod
    def _build_data_artifact(response: InvokeResponse) -> Artifact:
        return new_data_artifact("final-response", response.output_pydantic, "The final response")

    @staticmethod
    def _build_appropriate_artifact(response: InvokeResponse) -> Artifact:
        if response.output_pydantic:
            return RequestProcessor._build_data_artifact(response)
        else:
            return RequestProcessor._build_text_artifact(response)

    def _send_artifact(self, response: InvokeResponse) -> None:
        self.event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                contextId=self.context.context_id,
                taskId=self.context.task_id,
                append=False,
                lastChunk=True,
                artifact=self._build_appropriate_artifact(response),
                metadata=response.token_usage.__dict__,
            )
        )

    def _handle_canceled(self) -> None:
        self._update_task_status(
            TaskState.canceled,
            final=True,
            status_message="Task was cancelled by the user.",
        )

    def _handle_task_completed(
        self, response: InvokeResponse, classification: A2AResponseClassification
    ) -> None:
        self._send_artifact(response)
        self._update_task_status(
            TaskState.completed,
            final=True,
            status_message=classification.message if classification.message else None,
        )

    def _handle_task_input_required(
        self, response: InvokeResponse, classification: A2AResponseClassification
    ) -> None:
        self._update_task_status(
            TaskState.input_required, final=True, status_message=response.output_raw
        )

    def _handle_task_auth_required(
        self, response: InvokeResponse, classification: A2AResponseClassification
    ) -> None:
        status_message = ""
        if classification.message:
            status_message = f"{classification.message}\n\n"
        if classification.auth_details:
            status_message = f"{status_message}{classification.auth_details}\n\n"
        status_message = f"{status_message}{response.output_raw}"
        self._update_task_status(TaskState.auth_required, final=True, status_message=status_message)

    def _handle_task_failed(
        self, response: InvokeResponse, classification: A2AResponseClassification
    ) -> None:
        status_message: str | None
        if classification.message:
            status_message = classification.message
        else:
            status_message = response.output_raw

        self._update_task_status(TaskState.failed, final=True, status_message=status_message)

    def _handle_task_unknown(
        self, response: InvokeResponse, classification: A2AResponseClassification
    ) -> None:
        status_message: str | None
        if classification.message:
            status_message = classification.message
        else:
            status_message = response.output_raw

        self._update_task_status(TaskState.unknown, final=True, status_message=status_message)

    def _update_task_status(
        self,
        state: TaskState,
        final: bool = False,
        status_message: str | None = None,
    ) -> None:
        self.event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                contextId=self.context.context_id,
                taskId=self.context.task_id,
                final=final,
                status=TaskStatus(
                    state=state,
                    message=(new_agent_text_message(status_message) if status_message else None),
                ),
            )
        )
