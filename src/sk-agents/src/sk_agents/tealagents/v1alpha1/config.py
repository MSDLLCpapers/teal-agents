from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    model: str
    system_prompt: str
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    plugins: list[str] | None = None
    remote_plugins: list[str] | None = None
