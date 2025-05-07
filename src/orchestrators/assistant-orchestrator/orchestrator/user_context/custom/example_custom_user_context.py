import json

import redis
from ska_utils import AppConfig

from configs import (
    TA_REDIS_DB,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_TTL,
    TA_USER_INFORMATION_SOURCE_KEY,
)
from user_context.in_memory_context import ContextCacheResponse, UserContextCache


class ExampleCustomUserContext(UserContextCache):
    def __init__(self):
        self.app_config = AppConfig()
        self.redis_client = redis.Redis(
            host=self.app_config.get(TA_REDIS_HOST.env_name),
            port=int(self.app_config.get(TA_REDIS_PORT.env_name)),
            decode_responses=True,
            db=int(self.app_config.get(TA_REDIS_DB.env_name)),
        )
        self.ttl = int(self.app_config.get(TA_REDIS_TTL.env_name))
        self.user_information_api_key = self.app_config.get(TA_USER_INFORMATION_SOURCE_KEY.env_name)

    def get_user_context_from_cache(self, user_id: str) -> ContextCacheResponse:
        try:
            if self.redis_client.exists(user_id):
                context_cache = self.redis_client.get(user_id)
            else:
                user_context = self.fetch_user_information(user_id=user_id)
                if not user_context:
                    return ContextCacheResponse(user_context=None)
                self.redis_client.set(name=user_id, value=json.dumps(user_context), ex=self.ttl)
                context_cache = self.redis_client.get(user_id)

            return ContextCacheResponse(user_context=json.loads(context_cache))
        except Exception as e:
            print(f"User context not available. Error message: {e}")
            return ContextCacheResponse(user_context=None)

    def fetch_user_information(self, user_id: str) -> dict:
        api_key_for_user_information_source = self.user_information_api_key
        return {"user_id": user_id}
