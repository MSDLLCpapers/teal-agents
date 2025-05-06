from redis import Redis


class RedisStreamsEventPublisher:
    def __init__(self, r: Redis):
        self._r = r

    def publish_event(self, topic_name: str, event_data: str):
        self._r.xadd(name=topic_name, fields={"event_data": event_data})
