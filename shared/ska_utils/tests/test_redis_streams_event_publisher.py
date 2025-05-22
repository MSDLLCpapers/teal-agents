from unittest.mock import MagicMock

from redis import Redis

from ska_utils import RedisStreamsEventPublisher


def test_redis_streams_event_publisher_init():
    mock_redis = MagicMock(spec=Redis)
    publisher = RedisStreamsEventPublisher(mock_redis)
    assert publisher._r == mock_redis


def test_publish_event():
    mock_redis = MagicMock(spec=Redis)
    publisher = RedisStreamsEventPublisher(mock_redis)
    topic_name = "test_topic"
    event_data = "test_event_data"
    publisher.publish_event(topic_name, event_data)
    mock_redis.xadd.assert_called_once_with(name=topic_name, fields={"event_data": event_data})
