from pynamodb.attributes import UnicodeAttribute
from pynamodb.models import Model

from model.dynamo import _get_host, _get_region, _get_table_name


class LastChatSession(Model):
    class Meta:
        table_name = _get_table_name("last_chat_session")
        region = _get_region()
        host = _get_host()

    orchestrator = UnicodeAttribute(hash_key=True)
    user_id = UnicodeAttribute(range_key=True)
    session_id = UnicodeAttribute()
