from ska_utils import Config

TA_API_KEY = Config(env_name="TA_API_KEY", is_required=True, default_value=None)
TA_SERVICE_CONFIG = Config(
    env_name="TA_SERVICE_CONFIG", is_required=True, default_value="agents/config.yaml"
)
TA_REMOTE_PLUGIN_PATH = Config(
    env_name="TA_REMOTE_PLUGIN_PATH", is_required=False, default_value=None
)
TA_TYPES_MODULE = Config(env_name="TA_TYPES_MODULE", is_required=False, default_value=None)
TA_PLUGIN_MODULE = Config(env_name="TA_PLUGIN_MODULE", is_required=False, default_value=None)
TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE = Config(
    env_name="TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE",
    is_required=False,
    default_value=None,
)
TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME = Config(
    env_name="TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME",
    is_required=False,
    default_value=None,
)
TA_STRUCTURED_OUTPUT_TRANSFORMER_MODEL = Config(
    env_name="TA_STRUCTURED_OUTPUT_TRANSFORMER_MODEL",
    is_required=False,
    default_value="gpt-4o",
)
TA_A2A_ENABLED = Config(env_name="TA_A2A_ENABLED", is_required=True, default_value="false")
TA_AGENT_BASE_URL = Config(
    env_name="TA_AGENT_BASE_URL",
    is_required=True,
    default_value="http://localhost:8000",
)
TA_PROVIDER_ORG = Config(
    env_name="TA_PROVIDER_ORG", is_required=True, default_value="My Organization"
)
TA_PROVIDER_URL = Config(
    env_name="TA_PROVIDER_URL", is_required=True, default_value="http://localhost:8000"
)
TA_A2A_OUTPUT_CLASSIFIER_MODEL = Config(
    env_name="TA_A2A_OUTPUT_CLASSIFIER_MODEL",
    is_required=False,
    default_value="gpt-4o-mini",
)
TA_STATE_MANAGEMENT = Config(
    env_name="TA_STATE_MANAGEMENT",
    is_required=True,
    default_value="in-memory",
)

TA_AUTHORIZER_MODULE = Config(
    env_name="TA_AUTHORIZER_MODULE",
    is_required=False,
    default_value=None,
)
TA_AUTHORIZER_CLASS = Config(
    env_name="TA_AUTHORIZER_CLASS",
    is_required=False,
    default_value=None,
)

TA_REDIS_HOST = Config(env_name="TA_REDIS_HOST", is_required=False, default_value=None)
TA_REDIS_PORT = Config(env_name="TA_REDIS_PORT", is_required=False, default_value=None)
TA_REDIS_DB = Config(env_name="TA_REDIS_DB", is_required=False, default_value=None)
TA_REDIS_TTL = Config(env_name="TA_REDIS_TTL", is_required=False, default_value=None)
TA_REDIS_SSL = Config(env_name="TA_REDIS_SSL", is_required=False, default_value="true")
TA_REDIS_PWD = Config(env_name="TA_REDIS_PWD", is_required=False, default_value=None)

TA_PERSISTENCE_MODULE = Config(
    env_name="TA_PERSISTENCE_MODULE",
    is_required=True,
    default_value="persistence/in_memory_persistence_manager.py",
)
TA_PERSISTENCE_CLASS = Config(
    env_name="TA_PERSISTENCE_CLASS",
    is_required=True,
    default_value="InMemoryPersistenceManager",
)
TA_PLUGIN_CATALOG_MODULE = Config(
    env_name="TA_PLUGIN_CATALOG_MODULE",
    is_required=False,
    default_value="src/sk_agents/plugin_catalog/local_plugin_catalog.py",
)

TA_PLUGIN_CATALOG_CLASS = Config(
    env_name="TA_PLUGIN_CATALOG_CLASS",
    is_required=False,
    default_value="FileBasedPluginCatalog",
)

TA_PLUGIN_CATALOG_FILE = Config(
    env_name="TA_PLUGIN_CATALOG_FILE",
    is_required=False,
    default_value="src/sk_agents/plugin_catalog/catalog.json",
)

configs: list[Config] = [
    TA_API_KEY,
    TA_SERVICE_CONFIG,
    TA_REMOTE_PLUGIN_PATH,
    TA_TYPES_MODULE,
    TA_PLUGIN_MODULE,
    TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE,
    TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME,
    TA_STRUCTURED_OUTPUT_TRANSFORMER_MODEL,
    TA_A2A_ENABLED,
    TA_AGENT_BASE_URL,
    TA_PROVIDER_ORG,
    TA_PROVIDER_URL,
    TA_A2A_OUTPUT_CLASSIFIER_MODEL,
    TA_STATE_MANAGEMENT,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_DB,
    TA_REDIS_TTL,
    TA_REDIS_SSL,
    TA_REDIS_PWD,
    TA_PERSISTENCE_MODULE,
    TA_PERSISTENCE_CLASS,
    TA_AUTHORIZER_CLASS,
    TA_AUTHORIZER_MODULE,
    TA_PLUGIN_CATALOG_CLASS,
    TA_PLUGIN_CATALOG_MODULE,
    TA_PLUGIN_CATALOG_FILE,
]
