from pynamodb.attributes import BooleanAttribute, NumberAttribute, UnicodeAttribute
from pynamodb.models import Model

from model.dynamo import _get_host, _get_region, _get_table_name


class Ticket(Model):
    class Meta:
        table_name = _get_table_name("ticket")
        region = _get_region()
        host = _get_host()

    orchestrator = UnicodeAttribute(hash_key=True)
    ticket = UnicodeAttribute(range_key=True)
    user_id = UnicodeAttribute()
    ip_address = UnicodeAttribute()
    timestamp = NumberAttribute()
    used = BooleanAttribute()
