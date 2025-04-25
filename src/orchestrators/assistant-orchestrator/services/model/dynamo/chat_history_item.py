from pynamodb.attributes import NumberAttribute, UnicodeAttribute
from pynamodb.models import Model

from model.dynamo import _get_host, _get_region, _get_table_name


class ChatHistoryItem(Model):
    class Meta:
        table_name = _get_table_name("chat_history_item")
        region = _get_region()
        host = _get_host()

    session_id = UnicodeAttribute(hash_key=True)
    timestamp = NumberAttribute(range_key=True)
    orchestrator = UnicodeAttribute()
    agent_name = UnicodeAttribute()
    message_type = UnicodeAttribute()
    message = UnicodeAttribute()
