from pynamodb.attributes import UnicodeAttribute
from pynamodb.models import Model

from model.dynamo import _get_host, _get_region, _get_table_name


class ChatHistory(Model):
    class Meta:
        table_name = _get_table_name("chat_history")
        region = _get_region()
        host = _get_host()

    user_id = UnicodeAttribute(hash_key=True)
    session_id = UnicodeAttribute(range_key=True)
    orchestrator = UnicodeAttribute()
    previous_session = UnicodeAttribute(null=True)
