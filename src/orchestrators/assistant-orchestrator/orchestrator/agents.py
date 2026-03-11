import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable

import requests
import requests.exceptions
import websockets
from opentelemetry.propagate import inject
from pydantic import BaseModel, ConfigDict
from ska_utils import strtobool

from model import Conversation

logger = logging.getLogger(__name__)


class AgentConnectionError(Exception):
    """Raised when an agent cannot be reached (down, DNS failure, refused)."""
    def __init__(self, agent_name: str, message: str = ""):
        self.agent_name = agent_name
        self.message = message or f"Agent '{agent_name}' is not available or cannot be reached."
        super().__init__(self.message)


class AgentTimeoutError(Exception):
    """Raised when an agent does not respond within the timeout period."""
    def __init__(self, agent_name: str, message: str = ""):
        self.agent_name = agent_name
        self.message = message or f"Agent '{agent_name}' timed out while processing the request."
        super().__init__(self.message)


class AgentResponseError(Exception):
    """Raised when an agent returns a non-200 response."""
    def __init__(self, agent_name: str, status_code: int, detail: str = ""):
        self.agent_name = agent_name
        self.status_code = status_code
        self.detail = detail
        self.message = f"Agent '{agent_name}' returned an error (HTTP {status_code}): {detail}"
        super().__init__(self.message)


class AgentInvalidResponseError(Exception):
    """Raised when an agent returns a response that cannot be parsed."""
    def __init__(self, agent_name: str, message: str = ""):
        self.agent_name = agent_name
        self.message = message or f"Agent '{agent_name}' returned an invalid or unparseable response."
        super().__init__(self.message)


class MultiModalItem(BaseModel):
    content_type: str
    content: str


class ChatHistoryMultiModalItem(BaseModel):
    role: str
    items: list[MultiModalItem]


class ChatHistoryItem(BaseModel):
    role: str
    content: str


class AgentInput(BaseModel):
    chat_history: list[ChatHistoryItem | ChatHistoryMultiModalItem]
    user_context: dict[str, str]


def _conversation_to_agent_input(
    conv: Conversation, image_data: list[str] | str | None
) -> AgentInput:
    chat_history: list[ChatHistoryItem | ChatHistoryMultiModalItem] = []
    for idx, item in enumerate(conv.history):
        if image_data:
            if "data:image" in image_data or "string" not in image_data:
                if idx == len(conv.history) - 1:
                    image_items = []
                    # Handle both string and list of strings for image_data
                    if isinstance(image_data, list):
                        for img in image_data:
                            image_items.append(MultiModalItem(content_type="image", content=img))
                    else:
                        image_items.append(MultiModalItem(content_type="image", content=image_data))
                    chat_history.append(
                        ChatHistoryMultiModalItem(
                            role="user",
                            items=[MultiModalItem(content_type="text", content=item.content)]
                            + image_items,
                        )
                    )
            else:
                chat_history.append(
                    ChatHistoryMultiModalItem(
                        role="user",
                        items=[MultiModalItem(content_type="text", content=item.content)],
                    )
                )

        elif hasattr(item, "recipient"):
            # Create a ChatHistoryItem for user messages (simple format)
            chat_history.append(ChatHistoryItem(role="user", content=item.content))
        elif hasattr(item, "sender"):
            # Create a ChatHistoryItem for assistant messages (simple format)
            chat_history.append(ChatHistoryItem(role="assistant", content=item.content))

    # Build user_context
    user_context: dict[str, str] = {}
    for key, item in conv.user_context.items():
        user_context[key] = item.value

    # Return AgentInput
    return AgentInput(chat_history=chat_history, user_context=user_context)


class BaseAgent(ABC, BaseModel):
    name: str
    description: str
    endpoint: str
    endpoint_api: str
    api_key: str

    @abstractmethod
    def get_invoke_input(self, agent_input: AgentInput) -> str:
        pass

    async def invoke_stream(
        self, conv: Conversation, authorization: str | None = None
    ) -> AsyncIterable[str]:
        base_input = _conversation_to_agent_input(conv, None)
        input_message = self.get_invoke_input(base_input)

        headers = {
            "taAgwKey": self.api_key,
            "Authorization": authorization,
        }
        inject(headers)
        try:
            async with websockets.connect(self.endpoint, additional_headers=headers) as ws:
                await ws.send(input_message)
                async for message in ws:
                    yield message
        except (OSError, ConnectionRefusedError, websockets.exceptions.InvalidURI) as e:
            logger.error(f"Agent '{self.name}' is unreachable via WebSocket at {self.endpoint}: {e}")
            raise AgentConnectionError(self.name, f"Agent '{self.name}' is not available via WebSocket at {self.endpoint}. The agent may be down or unreachable.") from e
        except websockets.exceptions.WebSocketException as e:
            logger.error(f"WebSocket error with agent '{self.name}': {e}")
            raise AgentConnectionError(self.name, f"WebSocket communication failed with agent '{self.name}': {e}") from e
        except TimeoutError as e:
            logger.error(f"Agent '{self.name}' timed out via WebSocket at {self.endpoint}: {e}")
            raise AgentTimeoutError(self.name, f"Agent '{self.name}' timed out while processing the request via WebSocket.") from e

    # Origianl
    def invoke_api(
        self,
        conv: Conversation,
        authorization: str | None = None,
        image_data: list[str] | str | None = None,
    ) -> dict:
        """Invoke the agent via an HTTP API call."""
        base_input = _conversation_to_agent_input(conv, image_data)
        input_message = self.get_invoke_input(base_input)

        headers = {
            "taAgwKey": self.api_key,
            "Authorization": authorization,
            "Content-Type": "application/json",
        }
        inject(headers)
        logger.info("Beginning response processing")

        try:
            response = requests.post(
                self.endpoint_api, data=input_message, headers=headers, timeout=120
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Agent '{self.name}' is unreachable at {self.endpoint_api}: {e}")
            raise AgentConnectionError(self.name, f"Agent '{self.name}' is not available at {self.endpoint_api}. The agent may be down or unreachable.") from e
        except requests.exceptions.Timeout as e:
            logger.error(f"Agent '{self.name}' timed out at {self.endpoint_api}: {e}")
            raise AgentTimeoutError(self.name, f"Agent '{self.name}' timed out while processing the request.") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to agent '{self.name}' failed: {e}")
            raise AgentConnectionError(self.name, f"Failed to communicate with agent '{self.name}': {e}") from e

        if response.status_code != 200:
            detail = ""
            try:
                error_body = response.json()
                detail = error_body.get("detail", response.text)
            except Exception:
                detail = response.text
            logger.error(f"Agent '{self.name}' returned HTTP {response.status_code}: {detail}")
            raise AgentResponseError(self.name, response.status_code, detail)

        try:
            result = response.json()
        except Exception as e:
            logger.error(f"Agent '{self.name}' returned invalid JSON: {e}")
            raise AgentInvalidResponseError(self.name, f"Agent '{self.name}' returned a response that could not be parsed as JSON.") from e

        logger.info("Final response complete")
        return result

    async def invoke_sse(
        self,
        conv: Conversation,
        authorization: str | None = None,
        image_data: list[str] | str | None = None,
    ) -> dict:
        """Invoke the agent via an HTTP API call for SSE response."""
        base_input = _conversation_to_agent_input(conv, image_data)
        input_message = self.get_invoke_input(base_input)

        headers = {
            "taAgwKey": self.api_key,
            "Authorization": authorization,
            "Content-Type": "application/json",
        }
        inject(headers)
        logger.info("Beginning response processing")

        try:
            response = requests.post(
                f"{self.endpoint_api}/sse", data=input_message, headers=headers, timeout=120
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Agent '{self.name}' is unreachable at {self.endpoint_api}/sse: {e}")
            raise AgentConnectionError(self.name, f"Agent '{self.name}' is not available at {self.endpoint_api}/sse. The agent may be down or unreachable.") from e
        except requests.exceptions.Timeout as e:
            logger.error(f"Agent '{self.name}' timed out at {self.endpoint_api}/sse: {e}")
            raise AgentTimeoutError(self.name, f"Agent '{self.name}' timed out while processing the request.") from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to agent '{self.name}' failed: {e}")
            raise AgentConnectionError(self.name, f"Failed to communicate with agent '{self.name}': {e}") from e

        if response.status_code != 200:
            detail = ""
            try:
                error_body = response.json()
                detail = error_body.get("detail", response.text)
            except Exception:
                detail = response.text
            logger.error(f"Agent '{self.name}' returned HTTP {response.status_code}: {detail}")
            raise AgentResponseError(self.name, response.status_code, detail)

        logger.info("Final response complete")
        # Iterate over the response content line by line and yield each decoded line.
        for line in response.iter_lines():
            yield line.decode("utf-8") + "\n"


class AgentCatalog(BaseModel):
    agents: dict[str, BaseAgent]


class PromptAgent(BaseModel):
    name: str
    description: str


class FallbackInput(AgentInput):
    agents: list[PromptAgent]


class FallbackAgent(BaseAgent):
    agent_catalog: AgentCatalog

    def __init__(self, **data):
        super().__init__(**data)

    def get_invoke_input(self, agent_input: AgentInput) -> str:
        agents: list[PromptAgent] = []
        for agent in self.agent_catalog.agents.values():
            agents.append(PromptAgent(name=agent.name, description=agent.description))
        fallback_input = FallbackInput(
            chat_history=agent_input.chat_history,
            user_context=agent_input.user_context,
            agents=agents,
        )
        return fallback_input.model_dump_json()


class RecipientChooserAgent(BaseAgent):
    agent_catalog: AgentCatalog

    def get_invoke_input(self, agent_input: AgentInput) -> str:
        return agent_input.model_dump_json()


class Agent(BaseAgent):
    def get_invoke_input(self, agent_input: AgentInput) -> str:
        return agent_input.model_dump_json()


class OpenApiPost(BaseModel):
    model_config = ConfigDict(extra="allow")
    description: str


class OpenApiPath(BaseModel):
    model_config = ConfigDict(extra="allow")
    post: OpenApiPost | None = None
    get: OpenApiPost | None = None


class OpenApiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    paths: dict[str, OpenApiPath]


class AgentBuilder:
    def __init__(self, agpt_gw_host: str, agpt_gw_secure: str):
        self.agpt_gw_host = agpt_gw_host
        self.agpt_gw_secure = strtobool(agpt_gw_secure)

    def _http_or_https(self) -> str:
        return "https" if self.agpt_gw_secure else "http"

    def _ws_or_wss(self) -> str:
        return "wss" if self.agpt_gw_secure else "ws"

    @staticmethod
    def _agent_to_path(agent_name: str):
        if ":" not in agent_name:
            raise Exception(f"Expected 'AgentName':version. Ex: ExampleAgent:0.1. Got {agent_name}")
        toks = agent_name.split(":")
        return f"{toks[0]}/{toks[1]}"

    def _get_agent_description(self, agent_name: str) -> str:
        response = requests.get(
            f"{self._http_or_https()}://{self.agpt_gw_host}/{AgentBuilder._agent_to_path(agent_name)}/openapi.json"
        )
        if response:
            response_payload = OpenApiResponse(**response.json())
            return next(iter(response_payload.paths.values())).post.description
        else:
            raise Exception(f"Failed to get agent description for {agent_name}")

    def build_agent(self, agent_name: str, api_key: str) -> Agent:
        description = self._get_agent_description(agent_name)
        return Agent(
            name=agent_name,
            description=description,
            endpoint=f"{self._ws_or_wss()}://{self.agpt_gw_host}/{AgentBuilder._agent_to_path(agent_name)}/stream",
            endpoint_api=f"{self._http_or_https()}://{self.agpt_gw_host}/{AgentBuilder._agent_to_path(agent_name)}",
            api_key=api_key,
        )

    def build_fallback_agent(
        self, agent_name: str, api_key: str, agent_catalog: AgentCatalog
    ) -> FallbackAgent:
        description = self._get_agent_description(agent_name)
        return FallbackAgent(
            name=agent_name,
            description=description,
            endpoint=f"{self._ws_or_wss()}://{self.agpt_gw_host}/{AgentBuilder._agent_to_path(agent_name)}/stream",
            endpoint_api=f"{self._http_or_https()}://{self.agpt_gw_host}/{AgentBuilder._agent_to_path(agent_name)}",
            api_key=api_key,
            agent_catalog=agent_catalog,
        )

    def build_recipient_chooser_agent(
        self, agent_name: str, api_key: str, agent_catalog: AgentCatalog
    ) -> RecipientChooserAgent:
        description = self._get_agent_description(agent_name)
        return RecipientChooserAgent(
            name=agent_name,
            description=description,
            endpoint=f"{self._http_or_https()}://{self.agpt_gw_host}/{AgentBuilder._agent_to_path(agent_name)}",
            endpoint_api=f"{self._http_or_https()}://{self.agpt_gw_host}/{AgentBuilder._agent_to_path(agent_name)}",
            api_key=api_key,
            agent_catalog=agent_catalog,
        )
