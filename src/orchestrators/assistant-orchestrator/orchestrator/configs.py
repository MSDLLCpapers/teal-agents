from ska_utils import Config

TA_AGW_KEY = Config(env_name="TA_AGW_KEY", is_required=True, default_value=None)
TA_AGW_HOST = Config(
    env_name="TA_AGW_HOST", is_required=True, default_value="localhost:8000"
)
TA_AGW_SECURE = Config(
    env_name="TA_AGW_SECURE", is_required=True, default_value="false"
)
TA_SERVICE_CONFIG = Config(
    env_name="TA_SERVICE_CONFIG", is_required=True, default_value="conf/config.yaml"
)
TA_AUTH_ENABLED = Config(
    env_name="TA_AUTH_ENABLED", is_required=True, default_value="false"
)
TA_SERVICES_TYPE = Config(
    env_name="TA_SERVICES_TYPE", is_required=True, default_value="internal"
)
TA_SERVICES_ENDPOINT = Config(
    env_name="TA_SERVICES_ENDPOINT", is_required=False, default_value=None
)
TA_SERVICES_TOKEN = Config(
    env_name="TA_SERVICES_TOKEN", is_required=False, default_value=None
)
TA_USER_INFORMATION_SOURCE_KEY = Config(
    env_name="TA_USER_INFORMATION_SOURCE_KEY", is_required=False, default_value=None
)
TA_REDIS_HOST = Config(
    env_name="TA_REDIS_HOST", is_required=False, default_value=None
)
TA_REDIS_PORT = Config(
    env_name="TA_REDIS_PORT", is_required=False, default_value=None
)
TA_REDIS_DB = Config(
    env_name="TA_REDIS_DB", is_required=False, default_value=None
)
TA_REDIS_TTL = Config(
    env_name="TA_REDIS_TTL", is_required=False, default_value=None
)
TA_CUSTOM_USER_CONTEXT_ENABLED = Config(
    env_name="TA_CUSTOM_USER_CONTEXT_ENABLED", is_required=True, default_value=None
)
TA_CUSTOM_USER_CONTEXT_MODULE = Config(
    env_name="TA_CUSTOM_USER_CONTEXT_MODULE", is_required=False, default_value=None
)
TA_CUSTOM_USER_CONTEXT_CLASS_NAME = Config(
    env_name="TA_CUSTOM_USER_CONTEXT_CLASS_NAME", is_required=False, default_value=None
)

CONFIGS = [
    TA_AGW_KEY,
    TA_AGW_HOST,
    TA_AGW_SECURE,
    TA_SERVICE_CONFIG,
    TA_AUTH_ENABLED,
    TA_SERVICES_TYPE,
    TA_SERVICES_ENDPOINT,
    TA_SERVICES_TOKEN,
    TA_USER_INFORMATION_SOURCE_KEY,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_DB,
    TA_REDIS_TTL,
    TA_CUSTOM_USER_CONTEXT_ENABLED,
    TA_CUSTOM_USER_CONTEXT_MODULE,
    TA_CUSTOM_USER_CONTEXT_CLASS_NAME
]
