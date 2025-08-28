'''
class AppV3:
    @staticmethod
    def run(name, version, app_config, config, app):
        pass
'''

import os
from enum import Enum

from fastapi import FastAPI
from redis.asyncio import Redis
from ska_utils import AppConfig, strtobool

from sk_agents.configs import (
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
from sk_agents.ska_types import BaseConfig
from sk_agents.stateful import (
    InMemoryStateManager,
    MockAuthenticationManager,
    RedisStateManager,
    StateManager,
    UserMessage,
)
from sk_agents.utils import initialize_plugin_loader


class AppV3:
    class StateStores(Enum):
        IN_MEMORY = "in-memory"
        REDIS = "redis"

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
    def _get_auth_manager(app_config: AppConfig):
        # For initial implementation, use mock authentication
        # Will be extended in future for Entra ID
        return MockAuthenticationManager()

    @staticmethod
    def run(name: str, version: str, app_config: AppConfig, config: BaseConfig, app: FastAPI):
        if config.apiVersion != "tealagents/v1alpha1":
            raise ValueError(
                f"AppV3 only supports 'tealagents/v1alpha1' API version, got: {config.apiVersion}"
            )

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
                state_manager=state_manager,
                authorizer=auth_manager,
                input_class=UserMessage,
            ),
            prefix=f"/{name}/{version}",
        )

        # Make config and other essentials available to request handlers
        app.state.config = config
        app.state.app_config = app_config
