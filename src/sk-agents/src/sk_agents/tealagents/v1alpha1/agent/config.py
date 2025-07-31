from pydantic import BaseModel, ConfigDict

from sk_agents.ska_types import BaseConfig
from sk_agents.tealagents.v1alpha1.config import AgentConfig


# this may change base on ticket ticket CDW-917
class Spec(BaseModel):
    agent: AgentConfig


class v1alpha1Config(BaseConfig):
    model_config = ConfigDict(extra="allow")

    spec: Spec


class Config:
    def __init__(self, config: BaseConfig):
        self.config: v1alpha1Config = v1alpha1Config(
            apiVersion=config.apiVersion,
            description=config.description,
            service_name=config.service_name,
            version=config.version,
            input_type=config.input_type,
            spec=config.spec,
        )

    def get_agent(self) -> AgentConfig:
        return self.config.spec.agent
