from abc import ABC, abstractmethod

from pydantic import BaseModel


class ContextCacheResponse(BaseModel):
    user_context: dict | None


class UserContextCache(ABC):
    @abstractmethod
    def get_user_context_from_cache(self, user_id: str) -> ContextCacheResponse:
        pass

    @abstractmethod
    def fetch_user_information(self, user_id: str) -> dict:
        pass
