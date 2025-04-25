from ska_utils import Config

TA_DYNAMO_HOST = Config(env_name="TA_DYNAMO_HOST", is_required=False, default_value=None)
TA_KONG_ENABLED = Config(env_name="TA_KONG_ENABLED", is_required=True, default_value="false")
TA_VERIFY_IP = Config(env_name="TA_VERIFY_IP", is_required=True, default_value="false")

TA_ENVIRONMENT = Config(env_name="TA_ENVIRONMENT", is_required=False, default_value="dev")

TA_DYNAMO_TABLE_PREFIX = Config(
    env_name="TA_DYNAMO_TABLE_PREFIX", is_required=False, default_value=""
)

TA_DYNAMO_REGION = Config(env_name="TA_DYNAMO_REGION", is_required=False, default_value="us-east-1")

TA_CUSTOM_AUTH_ENABLED = Config(
    env_name="TA_CUSTOM_AUTH_ENABLED", is_required=True, default_value="false"
)

TA_CUSTOM_AUTH_MODULE = Config(
    env_name="TA_CUSTOM_AUTH_MODULE", is_required=False, default_value=None
)

TA_CUSTOM_AUTHENTICATOR = Config(
    env_name="TA_CUSTOM_AUTHENTICATOR", is_required=False, default_value=None
)

TA_CUSTOM_AUTH_REQUEST = Config(
    env_name="TA_CUSTOM_AUTH_REQUEST", is_required=False, default_value=None
)

CONFIGS = [
    TA_DYNAMO_HOST,
    TA_KONG_ENABLED,
    TA_VERIFY_IP,
    TA_ENVIRONMENT,
    TA_DYNAMO_TABLE_PREFIX,
    TA_DYNAMO_REGION,
    TA_CUSTOM_AUTH_ENABLED,
    TA_CUSTOM_AUTH_MODULE,
    TA_CUSTOM_AUTHENTICATOR,
    TA_CUSTOM_AUTH_REQUEST,
]
