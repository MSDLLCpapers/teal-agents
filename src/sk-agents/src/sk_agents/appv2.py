import os
from types import NoneType

from fastapi import FastAPI
from ska_utils import AppConfig

from sk_agents.configs import (
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
    def run(name: str, version: str, app_config: AppConfig, config: BaseConfig, app: FastAPI):
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
