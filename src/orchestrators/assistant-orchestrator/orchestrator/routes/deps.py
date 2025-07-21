from pydantic_yaml import parse_yaml_file_as
from ska_utils import AppConfig, initialize_telemetry

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
)
from connection_manager import ConnectionManager
from conversation_manager import ConversationManager
from jose_types import Config
from recipient_chooser import RecipientChooser
from session import AbstractSessionManager, InMemorySessionManager, RedisSessionManager
from user_context import CustomUserContextHelper, UserContextCache

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


def initialize() -> None:
    global \
        _conv_manager, \
        _conn_manager, \
        _session_manager, \
        _rec_chooser, \
        _config, \
        _agent_catalog, \
        _fallback_agent, \
        _user_context

    config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
    _config = parse_yaml_file_as(Config, config_file)

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
    _rec_chooser = RecipientChooser(recipient_chooser_agent)
    _user_context = _user_context_helper.get_user_context()


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
