import os
from types import NoneType

from fastapi import FastAPI
from ska_utils import AppConfig, strtobool

from sk_agents.a2a_event_handler import A2AEventHandler
from sk_agents.configs import (
    TA_A2A_EVENTS_ENABLED,
    TA_SERVICE_CONFIG,
)
from sk_agents.routes import Routes
from sk_agents.ska_types import (
    BaseConfig,
    BaseMultiModalInput,
)
from sk_agents.utils import initialize_plugin_loader


class AppV2:
    @staticmethod
    def run(
        name: str, version: str, app_config: AppConfig, config: BaseConfig, app: FastAPI
    ):
        is_v2 = strtobool(app_config.get(TA_A2A_EVENTS_ENABLED.env_name))
        config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
        agents_path = str(os.path.dirname(config_file))

        initialize_plugin_loader(agents_path=agents_path, app_config=app_config)

        root_handler = config.apiVersion.split("/")[0]

        if config.metadata is not None and config.metadata.description is not None:
            description = config.metadata.description
        else:
            description = f"{config.name} API"

        events_enabled = strtobool(app_config.get(TA_A2A_EVENTS_ENABLED.env_name))
        if events_enabled:
            event_handler = A2AEventHandler(
                app_config=app_config, config=config, root_handler=root_handler
            )
            app.add_event_handler("startup", event_handler.initialize)
            app.add_event_handler("shutdown", event_handler.shutdown)

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
        if is_v2:
            app.include_router(
                Routes.get_a2a_rest_routes(
                    name=name,
                    version=version,
                    description=description,
                    app_config=app_config,
                ),
                prefix=f"/{name}/{version}",
            )
