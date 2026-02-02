import json
import logging

import redis

from agents import BaseModel

from .session_manager import AbstractSessionManager, SessionData

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RedisSessionManager(AbstractSessionManager):
    """
    A Redis implementation of AbstractSessionManager.
    Session data is serialized to JSON before being stored in Redis.
    """

    def __init__(self, host: str, port: int, db: int = 0, ttl: int | None = None):
        """
        Initializes the RedisSessionManager.

        Args:
            host (str): The Redis server host.
            port (int): The Redis server port.
            db (int): The Redis database number to use (default is 0).
            ttl (Optional[int]): Time-to-live in seconds for session keys.
        """
        self.redis_client = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self.ttl = ttl
        logger.info(
            f"RedisSessionManager initialized with host={host}, port={port}, db={db}, ttl={ttl}."
        )

    async def add_session(self, session_id: str, data: SessionData) -> None:
        try:
            session_data_as_dict = {
                "conversation_id": data.conversation_id,
                "user_id": data.user_id,
                "request": data.request.model_dump()
                if isinstance(data.request, BaseModel)
                else data.request,
                "authorization": data.authorization.model_dump()
                if isinstance(data.authorization, BaseModel)
                else data.authorization,
            }
            final_json_string = json.dumps(session_data_as_dict)

            self.redis_client.set(session_id, final_json_string)
            if self.ttl:
                self.redis_client.expire(session_id, self.ttl)
            logger.info(f"Session '{session_id}' added/updated in Redis.")
        except Exception as e:
            logger.error(f"Error adding session '{session_id}' to Redis: {e}")
            raise

    async def get_session(self, session_id: str) -> SessionData | None:
        try:
            json_string_from_redis = self.redis_client.get(session_id)
            print(json_string_from_redis)
            if json_string_from_redis:
                # load the outer JSON string into a dictionary and parse back to pydantic model
                session_data_dict = json.loads(json_string_from_redis)
                conversation_obj = session_data_dict.get("conversation_id")
                user_obj = session_data_dict.get("user_id")
                request_obj = session_data_dict.get("request")
                authorization_obj = session_data_dict.get("authorization")

                session_data = SessionData(
                    conversation_id=conversation_obj,
                    user_id=user_obj,
                    request=request_obj,
                    authorization=authorization_obj,
                )
                logger.info(f"Session '{session_id}' retrieved from Redis.")
                return session_data
            else:
                logger.info(f"Session '{session_id}' not found in Redis.")
                return None
        except Exception as e:
            logger.error(f"Error retrieving session '{session_id}' from Redis: {e}")
            raise

    async def delete_session(self, session_id: str) -> None:
        try:
            deleted_count = self.redis_client.delete(session_id)
            if deleted_count > 0:
                logger.info(f"Session '{session_id}' deleted from Redis.")
            else:
                logger.info(f"Session '{session_id}' not found in Redis, nothing to delete.")
        except Exception as e:
            logger.error(f"Error deleting session '{session_id}' from Redis: {e}")
            raise
