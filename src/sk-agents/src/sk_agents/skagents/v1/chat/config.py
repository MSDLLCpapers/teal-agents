from pydantic import BaseModel, ConfigDict

from sk_agents.ska_types import BaseConfig
from sk_agents.skagents.v1.config import AgentConfig


class Spec(BaseModel):
    agent: AgentConfig


class V1Config(BaseConfig):
    model_config = ConfigDict(extra="allow")

    spec: Spec


class Config:
    def __init__(self, config: BaseConfig):
        self.config: V1Config = V1Config(
            apiVersion=config.apiVersion,
            description=config.description,
            service_name=config.service_name,
            version=config.version,
            input_type=config.input_type,
            spec=config.spec,
        )

    def get_agent(self) -> AgentConfig:
        return self.config.spec.agent
