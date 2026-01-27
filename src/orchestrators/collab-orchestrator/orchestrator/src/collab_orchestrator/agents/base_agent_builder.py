import aiohttp
from pydantic import BaseModel, ConfigDict

from collab_orchestrator.agents.agent_gateway import AgentGateway
from collab_orchestrator.agents.agent_types import BaseAgent


class OpenApiPost(BaseModel):
    model_config = ConfigDict(extra="allow")
    description: str | None = None


class OpenApiPath(BaseModel):
    model_config = ConfigDict(extra="allow")
    post: OpenApiPost | None = None
    get: OpenApiPost | None = None

class OpenApiResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    paths: dict[str, OpenApiPath]


class BaseAgentBuilder:
    def __init__(self, gateway: AgentGateway):
        self.gateway = gateway

    def _http_or_https(self) -> str:
        return "https" if self.gateway.secure else "http"

    @staticmethod
    def _agent_to_path(agent_name: str):
        toks = agent_name.split(":")
        return f"{toks[0]}/{toks[1]}"

    async def _get_agent_description(self, agent_name: str) -> str:
        async with aiohttp.ClientSession() as session:
            agent_path = BaseAgentBuilder._agent_to_path(agent_name)
            async with session.get(
                f"{self._http_or_https()}://{self.gateway.host}/{agent_path}/openapi.json"
            ) as response:
                if response.status != 200:
                    raise Exception(f"Failed to get agent description for {agent_name}")
                response_json = await response.json()
                response_payload = OpenApiResponse(**response_json)
                return response_payload.paths[f"/{agent_path}"].post.description

    async def build_agent(self, agent_full_name: str) -> BaseAgent:
        description = await self._get_agent_description(agent_full_name)

        toks = agent_full_name.split(":")
        agent_name = toks[0]
        agent_version = toks[1]
        return BaseAgent(
            name=agent_name,
            version=agent_version,
            description=description,
        )
