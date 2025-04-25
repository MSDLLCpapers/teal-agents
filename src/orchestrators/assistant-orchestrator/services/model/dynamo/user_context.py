from pynamodb.attributes import UnicodeAttribute
from pynamodb.models import Model

from model.dynamo import _get_host, _get_region, _get_table_name


class UserContext(Model):
    class Meta:
        table_name = _get_table_name("user_context")
        region = _get_region()
        host = _get_host()

    orchestrator_user_id = UnicodeAttribute(hash_key=True)
    context_key = UnicodeAttribute(range_key=True)
    context_value = UnicodeAttribute()
