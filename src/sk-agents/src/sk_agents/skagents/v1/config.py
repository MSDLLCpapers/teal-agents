from pydantic import BaseModel, ConfigDict, Field


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    model: str
    temperature: float | None = Field(None, ge=0.0, le=1.0)
    max_tokens: int | None = None
    system_prompt: str
    plugins: list[str] | None = None
    remote_plugins: list[str] | None = None
