from abc import ABC, abstractmethod
from typing import AsyncIterable, Dict, List

import requests
import websockets
from opentelemetry.propagate import inject
from pydantic import BaseModel, ConfigDict
from ska_utils import strtobool

from model import Conversation


class ChatHistoryItem(BaseModel):
    role: str
    content: str


class AgentInput(BaseModel):
    chat_history: List[ChatHistoryItem]
    user_context: Dict[str, str]


def _conversation_to_agent_input(conv: Conversation) -> AgentInput:
    chat_history: List[ChatHistoryItem] = []
    for item in conv.history:
        if hasattr(item, "recipient"):
            chat_history.append(ChatHistoryItem(role="user", content=item.content))
        elif hasattr(item, "sender"):
            chat_history.append(ChatHistoryItem(role="assistant", content=item.content))
    user_context: Dict[str, str] = {}
    for key, item in conv.user_context.items():
        user_context[key] = item.value
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
        base_input = _conversation_to_agent_input(conv)
        input_message = self.get_invoke_input(base_input)

        headers = {
            "taAgwKey": self.api_key,
            "Authorization": authorization,
        }
        inject(headers)
        async with websockets.connect(self.endpoint, additional_headers=headers) as ws:
            await ws.send(input_message)
            async for message in ws:
                yield message

    def invoke_api(
        self, conv: Conversation, authorization: str | None = None
    ) -> AsyncIterable[str]:
        """Invoke the agent via an HTTP API call."""
        base_input = _conversation_to_agent_input(conv)
        input_message = self.get_invoke_input(base_input)

        headers = {
            "taAgwKey": self.api_key,
            "Authorization": authorization,
            "Content-Type": "application/json",
        }
        response = requests.post(self.endpoint_api, data=input_message, headers=headers)

        if response.status_code != 200:
            raise Exception(
                f"Failed to invoke agent API: {response.status_code} - {response.text}"
            )

        return response.json()


class AgentCatalog(BaseModel):
    agents: Dict[str, BaseAgent]


class PromptAgent(BaseModel):
    name: str
    description: str


class FallbackInput(AgentInput):
    agents: List[PromptAgent]


class FallbackAgent(BaseAgent):
    agent_catalog: AgentCatalog

    def __init__(self, **data):
        super().__init__(**data)

    def get_invoke_input(self, agent_input: AgentInput) -> str:
        agents: List[PromptAgent] = []
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
    post: OpenApiPost


class OpenApiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    paths: Dict[str, OpenApiPath]


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
