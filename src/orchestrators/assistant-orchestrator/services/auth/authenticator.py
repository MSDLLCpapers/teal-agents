from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class AuthResponse(BaseModel):
    success: bool
    orch_name: str
    user_id: str


class Authenticator(ABC, Generic[T]):
    @abstractmethod
    def authenticate(self, orchestrator_name: str, request: T) -> AuthResponse:
        pass
