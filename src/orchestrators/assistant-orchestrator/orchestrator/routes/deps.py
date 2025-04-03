from contextlib import nullcontext
from typing import Dict, Tuple, Optional
from pydantic_yaml import parse_yaml_file_as
from ska_utils import AppConfig, initialize_telemetry
from agents import Agent, AgentBuilder, AgentCatalog
from configs import (
    CONFIGS,
    TA_SERVICE_CONFIG,
    TA_AGW_KEY,
    TA_AGW_HOST,
    TA_AGW_SECURE,
)
from conversation_manager import ConversationManager
from recipient_chooser import RecipientChooser
from connection_manager import ConnectionManager
from jose_types import Config
from user_context import CustomUserContextHelper, UserContextCache

AppConfig.add_configs(CONFIGS)

app_config = AppConfig()

_conv_manager: Optional[ConversationManager] = None
_conn_manager: Optional[ConnectionManager] = None
_rec_chooser: Optional[RecipientChooser] = None
_config: Optional[Config] = None
_agent_catalog: Optional[AgentCatalog] = None
_fallback_agent: Optional[Agent] = None
_user_context_helper: CustomUserContextHelper = CustomUserContextHelper(app_config)


def initialize() -> None:
    global _conv_manager, _conn_manager, _rec_chooser, _config, _agent_catalog, _fallback_agent, _user_context
    
    config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
    _config = parse_yaml_file_as(Config, config_file)

    initialize_telemetry(_config.service_name, app_config)

    api_key = app_config.get(TA_AGW_KEY.env_name)
    agent_builder = AgentBuilder(
        app_config.get(TA_AGW_HOST.env_name),
        app_config.get(TA_AGW_SECURE.env_name),
    )
    agents: Dict[str, Agent] = {}
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
    _rec_chooser = RecipientChooser(recipient_chooser_agent)
    _user_context = (
        _user_context_helper.get_user_context()
    )
def get_conv_manager() -> ConversationManager:
    if _conv_manager is None:
        initialize()
    return _conv_manager

def get_conn_manager() -> ConnectionManager:
    if _conn_manager is None:
        initialize()
    return _conn_manager

def get_rec_chooser() -> RecipientChooser:
    if _rec_chooser is None:
        initialize()
    return _rec_chooser

def get_config() -> Config:
    if _config is None:
        initialize()
    return _config

def get_agent_catalog() -> AgentCatalog:
    if _agent_catalog is None:
        initialize()
    return _agent_catalog

def get_fallback_agent() -> Agent:
    if _fallback_agent is None:
        initialize()
    return _fallback_agent

def get_user_context_cache() -> UserContextCache|None:
    if _user_context is None:
        initialize()
    return _user_context