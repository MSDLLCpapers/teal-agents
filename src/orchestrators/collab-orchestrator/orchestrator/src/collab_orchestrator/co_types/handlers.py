from pydantic import BaseModel


class AbortResult(BaseModel):
    session_id: str | None = None
    source: str | None = None
    request_id: str | None = None

    abort_reason: str
