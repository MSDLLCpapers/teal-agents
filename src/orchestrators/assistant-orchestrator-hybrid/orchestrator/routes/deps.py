from pydantic_yaml import parse_yaml_file_as
from ska_utils import AppConfig, initialize_telemetry

import logging

from agents import Agent, AgentBuilder, AgentCatalog
from configs import (
    CONFIGS,
    TA_AGW_HOST,
    TA_AGW_KEY,
    TA_AGW_SECURE,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_SESSION_DB,
    TA_REDIS_SESSION_TTL,
    TA_SERVICE_CONFIG,
    TA_SESSION_TYPE,
    # Semantic Search and ChromaDB configs
    TA_ENABLE_SEMANTIC_SEARCH,
    CHROMA_PERSIST_DIR,
    CHROMA_COLLECTION_NAME,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    BM25_WEIGHT,
    SEMANTIC_WEIGHT,
    # Agent Registration configs
    EMBEDDING_SIZE,
    DEFAULT_DEPLOYMENT_NAME,
)
from connection_manager import ConnectionManager
from conversation_manager import ConversationManager
from jose_types import Config
from recipient_chooser import RecipientChooser
from services.agent_registry_manager import AgentRegistryManager
from session import AbstractSessionManager, InMemorySessionManager, RedisSessionManager
from user_context import CustomUserContextHelper, UserContextCache

# Import new services and clients
from integration.chroma_client import ChromaClient
from integration.openai_client import AzureOpenAIClient
from services.hybrid_search_service import HybridSearchService
from services.agent_orchestration_service import AgentOrchestrationService, create_orchestration_service
from services.agent_registry_manager import AgentRegistryManager
from services.tfidf_service import TfidfLearningService
logger = logging.getLogger(__name__)

AppConfig.add_configs(CONFIGS)

app_config = AppConfig()

_conv_manager: ConversationManager | None = None
_conn_manager: ConnectionManager | None = None
_session_manager: AbstractSessionManager | None = None
_rec_chooser: RecipientChooser | None = None
_config: Config | None = None
_agent_catalog: AgentCatalog | None = None
_fallback_agent: Agent | None = None
_user_context_helper: CustomUserContextHelper = CustomUserContextHelper(app_config)
_user_context: UserContextCache | None = None


# New service instances
_chroma_client: ChromaClient | None = None
_openai_client: AzureOpenAIClient | None = None
_hybrid_search_service: HybridSearchService | None = None
_orchestration_service: AgentOrchestrationService | None = None
_agent_registry_manager: AgentRegistryManager | None = None
_tfidf_service: TfidfLearningService | None = None
_agent_registry_manager: AgentRegistryManager | None = None


def initialize() -> None:
    global \
        _conv_manager, \
        _conn_manager, \
        _session_manager, \
        _rec_chooser, \
        _config, \
        _agent_catalog, \
        _agent_registry_manager, \
        _fallback_agent, \
        _user_context, \
        _chroma_client, \
        _openai_client, \
        _hybrid_search_service, \
        _orchestration_service, \
        _agent_registry_manager, \
        _tfidf_service

    config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
    _config = parse_yaml_file_as(Config, config_file)
    embedding_size =   app_config.get("EMBEDDING_SIZE")
    default_deployment_name = app_config.get("DEFAULT_DEPLOYMENT_NAME")
    _agent_registry_manager = AgentRegistryManager(
        embedding_size=embedding_size,
        default_deployment_name=default_deployment_name,
    )

    if _config is None:
        raise TypeError("_config was None which should not happen")

    if _config.spec is None:
        raise TypeError("_config.spec was None which should not happen")

    initialize_telemetry(_config.service_name, app_config)

    api_key = app_config.get(TA_AGW_KEY.env_name)
    agent_builder = AgentBuilder(
        app_config.get(TA_AGW_HOST.env_name),
        app_config.get(TA_AGW_SECURE.env_name),
    )
    agents: dict[str, Agent] = {}
    for agent_name in _config.spec.agents:
        agents[agent_name] = agent_builder.build_agent(agent_name, api_key)
    _agent_catalog = AgentCatalog(agents=agents)

    _fallback_agent = agent_builder.build_fallback_agent(
        _config.spec.fallback_agent, api_key, _agent_catalog
    )
    recipient_chooser_agent = agent_builder.build_recipient_chooser_agent(
        _config.spec.agent_chooser, api_key, _agent_catalog
    )

    _conn_manager = ConnectionManager()
    _conv_manager = ConversationManager(_config.service_name)
    if app_config.get(TA_SESSION_TYPE.env_name) == "external":
        _session_manager = RedisSessionManager(
            app_config.get(TA_REDIS_HOST.env_name),
            app_config.get(TA_REDIS_PORT.env_name),
            app_config.get(TA_REDIS_SESSION_DB.env_name),
            app_config.get(TA_REDIS_SESSION_TTL.env_name),
        )
    else:
        _session_manager = InMemorySessionManager()
    _user_context = _user_context_helper.get_user_context()
    
    # Initialize OpenAI client (always needed for orchestration)
    _openai_client = AzureOpenAIClient()
    
    # Initialize orchestration service
    _orchestration_service = create_orchestration_service(_openai_client)
    
    # Conditionally initialize ChromaClient and HybridSearchService based on TA_ENABLE_SEMANTIC_SEARCH
    enable_semantic_search = app_config.get(TA_ENABLE_SEMANTIC_SEARCH.env_name).lower() == "true"
    
    if enable_semantic_search:
        logger.info("Semantic search ENABLED - initializing ChromaDB and HybridSearchService")
        _chroma_client = ChromaClient(
            persist_directory=app_config.get(CHROMA_PERSIST_DIR.env_name),
            collection_name=app_config.get(CHROMA_COLLECTION_NAME.env_name),
            embedding_model=app_config.get(AZURE_OPENAI_EMBEDDING_DEPLOYMENT.env_name)
        )
        
        _hybrid_search_service = HybridSearchService(
            chroma_client=_chroma_client,
            openai_client=_openai_client,
            bm25_weight=float(app_config.get(BM25_WEIGHT.env_name)),
            semantic_weight=float(app_config.get(SEMANTIC_WEIGHT.env_name))
        )
    else:
        logger.info("Semantic search DISABLED - skipping ChromaDB and HybridSearchService initialization")
        _chroma_client = None
        _hybrid_search_service = None
    
    # RecipientChooser can work with or without HybridSearchService and ChromaClient
    _rec_chooser = RecipientChooser(recipient_chooser_agent, _hybrid_search_service, _chroma_client)

    # Initialize AgentRegistryManager with config from environment
    _agent_registry_manager = AgentRegistryManager(
        embedding_size=int(app_config.get(EMBEDDING_SIZE.env_name)),
        default_deployment_name=app_config.get(DEFAULT_DEPLOYMENT_NAME.env_name),
    )


def get_conv_manager() -> ConversationManager:
    if _conv_manager is None:
        initialize()
        if _conv_manager is None:
            raise TypeError("_conv_manager is None")
    return _conv_manager


def get_conn_manager() -> ConnectionManager:
    if _conn_manager is None:
        initialize()
        if _conn_manager is None:
            raise TypeError("_conn_manager is None")
    return _conn_manager


def get_session_manager() -> AbstractSessionManager:
    if _session_manager is None:
        initialize()
        if _session_manager is None:
            raise TypeError("_session_manager is None")
    return _session_manager


def get_rec_chooser() -> RecipientChooser:
    if _rec_chooser is None:
        initialize()
        if _rec_chooser is None:
            raise TypeError("_rec_chooser is None")
    return _rec_chooser


def get_config() -> Config:
    if _config is None:
        initialize()
        if _config is None:
            raise TypeError("_config is None")
    return _config


def get_agent_catalog() -> AgentCatalog:
    if _agent_catalog is None:
        initialize()
        if _agent_catalog is None:
            raise TypeError("_agent_catalog is None")
    return _agent_catalog


def get_fallback_agent() -> Agent:
    if _fallback_agent is None:
        initialize()
        if _fallback_agent is None:
            raise TypeError("_fallback_agent is None")
    return _fallback_agent


def get_user_context_cache() -> UserContextCache | None:
    if _user_context is None:
        initialize()
    return _user_context


def get_chroma_client() -> ChromaClient | None:
    """
    Get ChromaDB client instance.
    
    Returns None if semantic search is disabled (TA_ENABLE_SEMANTIC_SEARCH=false).
    """
    if _chroma_client is None:
        initialize()
    return _chroma_client


def get_openai_client() -> AzureOpenAIClient:
    """Get Azure OpenAI client instance."""
    if _openai_client is None:
        initialize()
        if _openai_client is None:
            raise TypeError("_openai_client is None")
    return _openai_client


def get_hybrid_search_service() -> HybridSearchService | None:
    """
    Get HybridSearchService instance.
    
    Returns None if semantic search is disabled (TA_ENABLE_SEMANTIC_SEARCH=false).
    """
    if _hybrid_search_service is None:
        initialize()
    return _hybrid_search_service


def get_orchestration_service() -> AgentOrchestrationService:
    """Get AgentOrchestrationService instance."""
    if _orchestration_service is None:
        initialize()
        if _orchestration_service is None:
            raise TypeError("_orchestration_service is None")
    return _orchestration_service


def get_agent_registry_manager() -> AgentRegistryManager:
    """Get AgentRegistryManager instance."""
    if _agent_registry_manager is None:
        initialize()
        if _agent_registry_manager is None:
            raise TypeError("_agent_registry_manager is None")
    return _agent_registry_manager


def get_tfidf_learning_service() -> TfidfLearningService:
    """"TFIDF learning service"""
    global _tfidf_service
    if _tfidf_service is None:
        _tfidf_service = TfidfLearningService()
    return _tfidf_service