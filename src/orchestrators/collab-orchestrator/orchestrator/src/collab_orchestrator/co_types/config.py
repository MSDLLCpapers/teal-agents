from pydantic import BaseModel, ConfigDict


class SpecBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    agents: list[str]


class BaseConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    apiVersion: str
    kind: str
    description: str | None = None
    service_name: str
    version: float
    spec: SpecBase
