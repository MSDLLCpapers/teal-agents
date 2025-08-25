'''
class AppV3:
    @staticmethod
    def run(name, version, app_config, config, app):
        pass
'''

import os
from enum import Enum
from uuid import UUID

from fastapi import FastAPI, Depends
from redis.asyncio import Redis
from ska_utils import AppConfig, strtobool

from sk_agents.configs import (
    TA_AGENT_BASE_URL,
    TA_PROVIDER_ORG,
    TA_PROVIDER_URL,
    TA_REDIS_DB,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_PWD,
    TA_REDIS_SSL,
    TA_REDIS_TTL,
    TA_SERVICE_CONFIG,
    TA_STATE_MANAGEMENT,
)
from sk_agents.routes import Routes
from sk_agents.ska_types import (
    BaseConfig,
)
from sk_agents.stateful import (
    UserMessage,
    StateManager,
    InMemoryStateManager,
    RedisStateManager,
    AuthenticationManager,
    MockAuthenticationManager
)
from sk_agents.utils import initialize_plugin_loader
from sk_agents.a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentProvider,
    AgentSkill,
)


class AppV3:
    class StateStores(Enum):
        IN_MEMORY = "in-memory"
        REDIS = "redis"

    @staticmethod
    def get_url(name: str, version: str, app_config: AppConfig) -> str:
        base_url = app_config.get(TA_AGENT_BASE_URL.env_name)
        if not base_url:
            raise ValueError("Base URL is not provided in the app config.")
        return f"{base_url}/{name}/{version}"

    @staticmethod
    def get_provider(app_config: AppConfig) -> AgentProvider:
        return AgentProvider(
            organization=app_config.get(TA_PROVIDER_ORG.env_name),
            url=app_config.get(TA_PROVIDER_URL.env_name),
        )

    @staticmethod
    def get_agent_card(config: BaseConfig, app_config: AppConfig) -> AgentCard:
        if config.metadata is None:
            raise ValueError("Agent card metadata is not provided in the config.")
        if not config.name:
            raise ValueError("Agent name is not provided in the config.")

        metadata = config.metadata
        skills = [
            AgentSkill(
                id=skill.id,
                name=skill.name,
                description=skill.description,
                tags=skill.tags,
                examples=skill.examples,
                inputModes=skill.input_modes,
                outputModes=skill.output_modes,
            )
            for skill in metadata.skills
        ]
        return AgentCard(
            name=config.name,
            version=str(config.version),
            description=metadata.description,
            url=AppV3.get_url(config.name, str(config.version), app_config),
            provider=AppV3.get_provider(app_config),
            documentationUrl=config.metadata.documentation_url,
            capabilities=AgentCapabilities(
                streaming=True, pushNotifications=False, stateTransitionHistory=True
            ),
            defaultInputModes=["text"],
            defaultOutputModes=["text"],
            skills=skills,
        )

    @staticmethod
    def _get_redis_client(app_config: AppConfig) -> Redis:
        redis_host = app_config.get(TA_REDIS_HOST.env_name)
        redis_port = app_config.get(TA_REDIS_PORT.env_name)
        redis_db = app_config.get(TA_REDIS_DB.env_name)
        redis_ssl = strtobool(app_config.get(TA_REDIS_SSL.env_name))
        redis_pwd = app_config.get(TA_REDIS_PWD.env_name)

        if not redis_host:
            raise ValueError("Redis host must be provided for Redis state store.")
        if not redis_port:
            raise ValueError("Redis port must be provided for Redis state store.")

        return Redis(
            host=redis_host,
            port=int(redis_port),
            db=int(redis_db) if redis_db else 0,
            ssl=redis_ssl,
            password=redis_pwd if redis_pwd else None,
        )

    @staticmethod
    def _get_state_manager(app_config: AppConfig) -> StateManager:
        state_store = app_config.get(TA_STATE_MANAGEMENT.env_name)
        match state_store:
            case AppV3.StateStores.REDIS.value:
                redis_ttl = app_config.get(TA_REDIS_TTL.env_name)
                return RedisStateManager(
                    redis_client=AppV3._get_redis_client(app_config),
                    ttl=int(redis_ttl) if redis_ttl else None,
                )
            case _:
                return InMemoryStateManager()

    @staticmethod
    def _get_auth_manager(app_config: AppConfig) -> AuthenticationManager:
        # For initial implementation, use mock authentication (Extend in future for Entra ID)
        return MockAuthenticationManager()

    @staticmethod
    def run(name: str, version: str, app_config: AppConfig, config: BaseConfig, app: FastAPI):
        if config.apiVersion != "tealagents/v1alpha1":
            raise ValueError(f"AppV3 only supports 'tealagents/v1alpha1' API version, got: {config.apiVersion}")

        config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
        agents_path = str(os.path.dirname(config_file))

        initialize_plugin_loader(agents_path=agents_path, app_config=app_config)

        # Create state and auth managers
        state_manager = AppV3._get_state_manager(app_config)
        auth_manager = AppV3._get_auth_manager(app_config)

        # Get description from metadata if available
        if config.metadata is not None and config.metadata.description is not None:
            description = config.metadata.description
        else:
            description = f"{config.name} API"

        # Include only REST routes - No Websockets in V3
        app.include_router(
            Routes.get_stateful_routes(
                name=name,
                version=version,
                description=description,
                config=config,
                app_config=app_config,
                state_manager=state_manager,
                auth_manager=auth_manager,
                input_class=UserMessage,
            ),
            prefix=f"/{name}/{version}",
        )

        # Generate agent card for metadata
        try:
            agent_card = AppV3.get_agent_card(config, app_config)
            # Make agent card available to routes
            app.state.agent_card = agent_card
        except ValueError as e:
            # Log warning
            print(f"Warning: Could not generate agent card: {e}")