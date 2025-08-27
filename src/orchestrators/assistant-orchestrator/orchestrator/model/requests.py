from pydantic import BaseModel


class ConversationMessageRequest(BaseModel):
    message: str
    image_data: list[str] | str | None = None
