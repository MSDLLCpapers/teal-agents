import logging

from ska_utils import AppConfig, Singleton

from configs import TA_ENVIRONMENT
from data.context_manager import ContextManager
from model.dynamo.user_context import UserContext

logger = logging.getLogger(__name__)


class DynamoContextManager(ContextManager, metaclass=Singleton):
    def __init__(self):
        cfg = AppConfig()
        if cfg.get(TA_ENVIRONMENT.env_name) == "local":
            if not UserContext.exists():
                UserContext.create_table(read_capacity_units=1, write_capacity_units=1, wait=True)

    @staticmethod
    def _get_context_hash_key(orchestrator_name: str, user_id: str) -> str:
        return f"{orchestrator_name}#{user_id}"

    def add_context(self, orchestrator_name: str, user_id: str, item_key: str, item_value: str):
        context_item = UserContext(
            orchestrator_user_id=DynamoContextManager._get_context_hash_key(
                orchestrator_name, user_id
            ),
            context_key=item_key,
            context_value=item_value,
        )
        try:
            context_item.save()
        except Exception as e:
            logger.exception(f"Error adding context item to DB - Error: {e}")

    def update_context(self, orchestrator_name: str, user_id: str, item_key: str, item_value: str):
        context_item = UserContext(
            orchestrator_user_id=DynamoContextManager._get_context_hash_key(
                orchestrator_name, user_id
            ),
            context_key=item_key,
            context_value=item_value,
        )
        try:
            context_item.save()
        except Exception as e:
            logger.exception(f"Error updating context in DB - Error: {e}")

    def delete_context(self, orchestrator_name: str, user_id: str, item_key: str):
        item_to_delete = UserContext.get(
            DynamoContextManager._get_context_hash_key(orchestrator_name, user_id),
            item_key,
        )
        try:
            item_to_delete.delete()
        except Exception as e:
            logger.exception(f"Error deleting context from DB - Error: {e}")

    def get_context(self, orchestrator_name: str, user_id) -> dict[str, str]:
        context_items: dict[str, str] = {}
        try:
            for item in UserContext.query(
                DynamoContextManager._get_context_hash_key(orchestrator_name, user_id)
            ):
                context_items[item.context_key] = item.context_value
            return context_items
        except Exception as e:
            logger.exception(f"Error retrieving context from DB - Error: {e}")
