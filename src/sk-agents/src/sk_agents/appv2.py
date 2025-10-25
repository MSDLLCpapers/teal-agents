import os
from enum import Enum
from types import NoneType

from a2a.server.tasks import InMemoryTaskStore
from a2a.server.tasks.task_store import TaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentProvider, AgentSkill
from fastapi import FastAPI
from redis.asyncio import Redis
from ska_utils import AppConfig, strtobool

from sk_agents.a2a import RedisTaskStore
from sk_agents.configs import (
    TA_A2A_ENABLED,
    TA_A2A_OUTPUT_CLASSIFIER_MODEL,
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
    BaseMultiModalInput,
)
from sk_agents.skagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.state import InMemoryStateManager, RedisStateManager, StateManager
from sk_agents.utils import initialize_plugin_loader


# DEPRECATION NOTICE: AppV2 and its A2A (Agent-to-Agent) functionality is being deprecated
# as part of the framework migration evaluation. New development should avoid using A2A
# functionality. Existing A2A functionality will continue to work but is no longer actively
# developed.
class AppV2:
    class StateStores(Enum):
        IN_MEMORY = "in-memory"
        REDIS = "redis"

    @staticmethod
    def get_url(name: str, version: str, app_config: AppConfig) -> str:
        base_url = app_config.get(TA_AGENT_BASE_URL.env_name)
        if not base_url:
            raise ValueError("Base URL is not provided in the app config.")
        return f"{base_url}/{name}/{version}/a2a"

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
            url=AppV2.get_url(config.name, str(config.version), app_config),
            provider=AppV2.get_provider(app_config),
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
            raise ValueError("Redis host must be provided for Redis task store.")
        if not redis_port:
            raise ValueError("Redis port must be provided for Redis task store.")

        return Redis(
            host=redis_host,
            port=int(redis_port),
            db=int(redis_db) if redis_db else 0,
            ssl=redis_ssl,
            password=redis_pwd if redis_pwd else None,
        )

    @staticmethod
    def _get_redis_task_store(app_config: AppConfig) -> TaskStore:
        redis_ttl = app_config.get(TA_REDIS_TTL.env_name)

        return RedisTaskStore(
            redis_client=AppV2._get_redis_client(app_config),
            ttl=int(redis_ttl) if redis_ttl else None,
        )

    @staticmethod
    def _get_redis_state_manager(app_config: AppConfig) -> StateManager:
        redis_ttl = app_config.get(TA_REDIS_TTL.env_name)

        return RedisStateManager(
            redis_client=AppV2._get_redis_client(app_config),
            ttl=int(redis_ttl) if redis_ttl else None,
        )

    @staticmethod
    def _get_task_store(app_config: AppConfig) -> TaskStore:
        state_store = app_config.get(TA_STATE_MANAGEMENT.env_name)
        match state_store:
            case AppV2.StateStores.REDIS.value:
                return AppV2._get_redis_task_store(app_config)
            case _:
                return InMemoryTaskStore()

    @staticmethod
    def _get_state_manager(app_config: AppConfig) -> StateManager:
        state_store = app_config.get(TA_STATE_MANAGEMENT.env_name)
        match state_store:
            case AppV2.StateStores.REDIS.value:
                return AppV2._get_redis_state_manager(app_config)
            case _:
                return InMemoryStateManager()

    @staticmethod
    def run(name: str, version: str, app_config: AppConfig, config: BaseConfig, app: FastAPI):
        a2a_enabled = strtobool(app_config.get(TA_A2A_ENABLED.env_name))
        config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
        agents_path = str(os.path.dirname(config_file))

        initialize_plugin_loader(agents_path=agents_path, app_config=app_config)

        root_handler = config.apiVersion.split("/")[0]

        if config.metadata is not None and config.metadata.description is not None:
            description = config.metadata.description
        else:
            description = f"{config.name} API"

        app.include_router(
            Routes.get_rest_routes(
                name=name,
                version=version,
                description=description,
                root_handler_name=root_handler,
                config=config,
                app_config=app_config,
                input_class=BaseMultiModalInput,
                output_class=NoneType,
            ),
            prefix=f"/{name}/{version}",
        )
        app.include_router(
            Routes.get_websocket_routes(
                name=name,
                version=version,
                root_handler_name=root_handler,
                config=config,
                app_config=app_config,
                input_class=BaseMultiModalInput,
            ),
            prefix=f"/{name}/{version}",
        )
        if a2a_enabled:
            # DEPRECATION NOTICE: A2A (Agent-to-Agent) functionality is deprecated.
            # This code path is maintained for backward compatibility only.
            # Avoid using A2A functionality for new development.
            chat_completion_builder = ChatCompletionBuilder(app_config)
            chat_completion_builder.get_chat_completion_for_model(
                "test-to-confirm-model-availability",
                app_config.get(TA_A2A_OUTPUT_CLASSIFIER_MODEL.env_name),
            )
            task_store = AppV2._get_task_store(app_config)
            state_manager = AppV2._get_state_manager(app_config)
            app.include_router(
                Routes.get_a2a_routes(
                    name=name,
                    version=version,
                    description=description,
                    config=config,
                    app_config=app_config,
                    chat_completion_builder=chat_completion_builder,
                    task_store=task_store,
                    state_manager=state_manager,
                ),
                prefix=f"/{name}/{version}/a2a",
            )
