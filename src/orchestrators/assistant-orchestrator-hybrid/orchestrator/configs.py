from ska_utils import Config

TA_AGW_KEY = Config(env_name="TA_AGW_KEY", is_required=True, default_value=None)
TA_AGW_HOST = Config(env_name="TA_AGW_HOST", is_required=True, default_value="localhost:8000")
TA_AGW_SECURE = Config(env_name="TA_AGW_SECURE", is_required=True, default_value="false")
TA_SERVICE_CONFIG = Config(
    env_name="TA_SERVICE_CONFIG", is_required=True, default_value="conf/config.yaml"
)
TA_AUTH_ENABLED = Config(env_name="TA_AUTH_ENABLED", is_required=True, default_value="false")
TA_SERVICES_TYPE = Config(env_name="TA_SERVICES_TYPE", is_required=True, default_value="internal")
TA_SERVICES_ENDPOINT = Config(
    env_name="TA_SERVICES_ENDPOINT", is_required=False, default_value=None
)
TA_SERVICES_TOKEN = Config(env_name="TA_SERVICES_TOKEN", is_required=False, default_value=None)
TA_USER_INFORMATION_SOURCE_KEY = Config(
    env_name="TA_USER_INFORMATION_SOURCE_KEY", is_required=False, default_value=None
)
TA_REDIS_HOST = Config(env_name="TA_REDIS_HOST", is_required=False, default_value=None)
TA_REDIS_PORT = Config(env_name="TA_REDIS_PORT", is_required=False, default_value=None)
TA_REDIS_DB = Config(env_name="TA_REDIS_DB", is_required=False, default_value=None)
TA_REDIS_SESSION_DB = Config(env_name="TA_REDIS_SESSION_DB", is_required=False, default_value=None)
TA_REDIS_TTL = Config(env_name="TA_REDIS_TTL", is_required=False, default_value=None)
TA_REDIS_SESSION_TTL = Config(
    env_name="TA_REDIS_SESSION_TTL", is_required=False, default_value=None
)
TA_SESSION_TYPE = Config(env_name="TA_SESSION_TYPE", is_required=True, default_value="internal")
TA_CUSTOM_USER_CONTEXT_ENABLED = Config(
    env_name="TA_CUSTOM_USER_CONTEXT_ENABLED", is_required=True, default_value=None
)
TA_CUSTOM_USER_CONTEXT_MODULE = Config(
    env_name="TA_CUSTOM_USER_CONTEXT_MODULE", is_required=False, default_value=None
)
TA_CUSTOM_USER_CONTEXT_CLASS_NAME = Config(
    env_name="TA_CUSTOM_USER_CONTEXT_CLASS_NAME", is_required=False, default_value=None
)
###Celery config####
TA_CELERY_CONFIG = Config(env_name="TA_CELERY_CONFIG",
                        is_required=False,
                        default_value='redis://redis:6379/0')
# Semantic Search Configuration
TA_ENABLE_SEMANTIC_SEARCH = Config(
    env_name="TA_ENABLE_SEMANTIC_SEARCH", is_required=False, default_value="false"
)
TA_SEMANTIC_SEARCH_TOP_K = Config(
    env_name="TA_SEMANTIC_SEARCH_TOP_K", is_required=False, default_value="2"
)
TA_SEMANTIC_SEARCH_THRESHOLD = Config(
    env_name="TA_SEMANTIC_SEARCH_THRESHOLD", is_required=False, default_value="0.7"
)

# BM25 and Semantic Weights
BM25_WEIGHT = Config(env_name="BM25_WEIGHT", is_required=False, default_value="0.25")
SEMANTIC_WEIGHT = Config(env_name="SEMANTIC_WEIGHT", is_required=False, default_value="0.75")

# Query Expansion Configuration
TA_ENABLE_QUERY_EXPANSION = Config(
    env_name="TA_ENABLE_QUERY_EXPANSION", is_required=False, default_value="true"
)

# Follow-up Analysis Configuration
TA_ENABLE_FOLLOWUP_ANALYSIS = Config(
    env_name="TA_ENABLE_FOLLOWUP_ANALYSIS", is_required=False, default_value="true"
)
TA_FOLLOWUP_MAX_HISTORY = Config(
    env_name="TA_FOLLOWUP_MAX_HISTORY", is_required=False, default_value="2"
)

# Parallel Processing Configuration
TA_ENABLE_PARALLEL_PROCESSING = Config(
    env_name="TA_ENABLE_PARALLEL_PROCESSING", is_required=False, default_value="true"
)
TA_PARALLEL_MAX_AGENTS = Config(
    env_name="TA_PARALLEL_MAX_AGENTS", is_required=False, default_value="2"
)

# Azure OpenAI Configuration
AZURE_OPENAI_API_KEY = Config(
    env_name="AZURE_OPENAI_API_KEY", is_required=False, default_value=None
)
AZURE_OPENAI_ENDPOINT = Config(
    env_name="AZURE_OPENAI_ENDPOINT", is_required=False, default_value=None
)
AZURE_OPENAI_API_VERSION = Config(
    env_name="AZURE_OPENAI_API_VERSION", is_required=False, default_value="2024-02-01"
)
AZURE_OPENAI_CHAT_MODEL = Config(
    env_name="AZURE_OPENAI_CHAT_MODEL", is_required=False, default_value="gpt-4o-2024-11-20"
)
AZURE_OPENAI_RERANKER_MODEL = Config(
    env_name="AZURE_OPENAI_RERANKER_MODEL", is_required=False, default_value=None
)
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = Config(
    env_name="AZURE_OPENAI_EMBEDDING_DEPLOYMENT", is_required=False, default_value="text-embedding-3-small"
)

# Agent Registration Configuration
AGENT_REGISTRATION_TOKEN = Config(
    env_name="AGENT_REGISTRATION_TOKEN", is_required=False, default_value=""
)
DEFAULT_DEPLOYMENT_NAME = Config(
    env_name="DEFAULT_DEPLOYMENT_NAME", is_required=False, default_value="Talk"
)

# Database Configuration
DB_HOST = Config(
    env_name="DB_HOST", is_required=False, default_value="localhost"
)
DB_PORT = Config(
    env_name="DB_PORT", is_required=False, default_value="5432"
)
DB_NAME = Config(
    env_name="DB_NAME", is_required=False, default_value="agent_registry"
)
DB_USER = Config(
    env_name="DB_USER", is_required=False, default_value="postgres"
)
DB_PASSWORD = Config(
    env_name="DB_PASSWORD", is_required=False, default_value=""
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
    TA_REDIS_SESSION_DB,
    TA_REDIS_TTL,
    TA_REDIS_SESSION_TTL,
    TA_SESSION_TYPE,
    TA_CUSTOM_USER_CONTEXT_ENABLED,
    TA_CUSTOM_USER_CONTEXT_MODULE,
    TA_CUSTOM_USER_CONTEXT_CLASS_NAME,
    # Semantic Search
    TA_ENABLE_SEMANTIC_SEARCH,
    TA_SEMANTIC_SEARCH_TOP_K,
    TA_SEMANTIC_SEARCH_THRESHOLD,
    # Hybrid Search Weights
    BM25_WEIGHT,
    SEMANTIC_WEIGHT,
    # Query Expansion
    TA_ENABLE_QUERY_EXPANSION,
    # Follow-up Analysis
    TA_ENABLE_FOLLOWUP_ANALYSIS,
    TA_FOLLOWUP_MAX_HISTORY,
    # Parallel Processing
    TA_ENABLE_PARALLEL_PROCESSING,
    TA_PARALLEL_MAX_AGENTS,
    # Azure OpenAI
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_ENDPOINT,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_CHAT_MODEL,
    AZURE_OPENAI_RERANKER_MODEL,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    # Agent Registration
    AGENT_REGISTRATION_TOKEN,
    DEFAULT_DEPLOYMENT_NAME,
    # Database
    DB_HOST,
    DB_PORT,
    DB_NAME,
    DB_USER,
    DB_PASSWORD,
]
