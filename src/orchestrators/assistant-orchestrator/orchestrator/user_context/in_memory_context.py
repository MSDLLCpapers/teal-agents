from typing import Dict
from pydantic import BaseModel
from abc import ABC, abstractmethod

class ContextCacheResponse(BaseModel):
    user_context: Dict | None


class UserContextCache(ABC):
    
    @abstractmethod
    def get_user_context_from_cache(self, user_id:str) -> ContextCacheResponse:
        pass
    
    @abstractmethod
    def fetch_user_information(self, user_id:str) -> Dict:
        pass
    