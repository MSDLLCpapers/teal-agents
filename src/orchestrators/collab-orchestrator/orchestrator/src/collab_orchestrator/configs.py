from ska_utils import Config

TA_AGW_KEY = Config(env_name="TA_AGW_KEY", is_required=True, default_value=None)
TA_AGW_HOST = Config(env_name="TA_AGW_HOST", is_required=True, default_value="localhost:8000")
TA_AGW_SECURE = Config(env_name="TA_AGW_SECURE", is_required=True, default_value="false")
TA_SERVICE_CONFIG = Config(env_name="TA_SERVICE_CONFIG", is_required=True, default_value=None)
TA_REDIS_HOST = Config(env_name="TA_REDIS_HOST", is_required=False, default_value=None)
TA_REDIS_PORT = Config(env_name="TA_REDIS_PORT", is_required=False, default_value=None)
TA_REDIS_DB = Config(env_name="TA_REDIS_DB", is_required=False, default_value=None)
TA_REDIS_TTL = Config(env_name="TA_REDIS_TTL", is_required=False, default_value=None)

CONFIGS = [
    TA_AGW_KEY,
    TA_AGW_HOST,
    TA_AGW_SECURE,
    TA_SERVICE_CONFIG,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_DB,
    TA_REDIS_TTL,
]
