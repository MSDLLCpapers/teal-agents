import json
import logging
from typing import Generic, Type

import requests
import aiohttp
from dapr.ext.workflow import WorkflowActivityContext
from ska_utils import AppConfig, strtobool

from workflow_orchestrator import TAgentInput, TAgentOutput, AgentActivityInput
from workflow_orchestrator.configs import TA_AGW_SECURE, TA_AGW_HOST, TA_AGW_KEY


class AgentInvoker(Generic[TAgentInput, TAgentOutput]):
    def __init__(self, agent_name: str, agent_version: str):
        self.agent_name = agent_name
        self.agent_version = agent_version
        self.logger = logging.getLogger("agent-invoker")

        app_config = AppConfig()
        self.api_key = app_config.get(TA_AGW_KEY.env_name)
        self.agpt_gw_host = app_config.get(TA_AGW_HOST.env_name)
        self.agpt_gw_secure = strtobool(app_config.get(TA_AGW_SECURE.env_name))

    def _http_or_https(self) -> str:
        return "https" if self.agpt_gw_secure else "http"

    def _get_agent_endpoint(self) -> str:
        return f"{self._http_or_https()}://{self.agpt_gw_host}/{self.agent_name}/{self.agent_version}"

    async def invoke_agent(
        self, agent_input: TAgentInput, output_type: type[TAgentOutput] | None = None
    ) -> TAgentOutput | str:
        endpoint: str = self._get_agent_endpoint()
        headers = {"taAgwKey": self.api_key}
        self.logger.info(
            f"Invoking agent {self.agent_name}:{self.agent_version} at {endpoint}"
        )
        try:
            body_json = json.dumps(
                agent_input.__dict__
                if hasattr(agent_input, "__dict__")
                else agent_input
            )
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    endpoint,
                    data=body_json,
                    headers=headers,
                ) as response:
                    response.raise_for_status()
                    if output_type:
                        response_json = response.json()["output_pydantic"]
                        return output_type(**response_json)
                    else:
                        return response.json()["output_raw"]
        except Exception as e:
            self.logger.error(f"Error invoking agent: {str(e)}")
            return str(e)


def _serialize_type(type_: Type) -> dict:
    """Serializes a type object to a dictionary."""
    return {
        "name": type_.__name__,
        "module": type_.__module__,
    }


def _deserialize_type(data: dict) -> Type:
    """Deserializes a type object from a dictionary."""
    module_name = data["module"]
    type_name = data["name"]
    try:
        module = __import__(module_name, fromlist=[type_name])
        return getattr(module, type_name)
    except (ImportError, AttributeError):
        raise ValueError(f"Could not deserialize type: {data}")


def create_agent_input(
    agent_name: str,
    agent_version: str,
    agent_input: TAgentInput,
    output_type: type[TAgentOutput] | None = None,
):
    return AgentActivityInput(
        agent_name=agent_name,
        agent_version=agent_version,
        agent_input=agent_input,
        output_type=_serialize_type(output_type) if output_type else None,
    )


async def invoke_agent_task(
    ctx: WorkflowActivityContext, agent_input: AgentActivityInput
) -> TAgentOutput | str:
    if agent_input.output_type:
        output_type = _deserialize_type(agent_input.output_type)
    else:
        output_type = None
    agent_invoker = AgentInvoker(agent_input.agent_name, agent_input.agent_version)
    return await agent_invoker.invoke_agent(agent_input.agent_input, output_type)
