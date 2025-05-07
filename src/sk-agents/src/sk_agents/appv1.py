import os
from typing import Any

from fastapi import FastAPI
from ska_utils import AppConfig

from sk_agents.configs import (
    TA_SERVICE_CONFIG,
    TA_TYPES_MODULE,
)
from sk_agents.routes import Routes
from sk_agents.ska_types import (
    BaseConfig,
)
from sk_agents.type_loader import get_type_loader
from sk_agents.utils import initialize_plugin_loader


class AppV1:
    @staticmethod
    def run(name: str, version: str, app_config: AppConfig, config: BaseConfig, app: FastAPI):
        config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
        agents_path = str(os.path.dirname(config_file))

        types_module = app_config.get(TA_TYPES_MODULE.env_name)
        # If no types module has been defined:
        # Check if there is a custom_types.py file in the agents directory
        if types_module is None:
            custom_types = os.path.join(agents_path, "custom_types.py")
            if os.path.exists(custom_types):
                app_config.props[TA_TYPES_MODULE.env_name] = custom_types
                types_module = custom_types
        type_loader = get_type_loader(types_module)

        initialize_plugin_loader(agents_path=agents_path, app_config=app_config)

        root_handler = config.apiVersion.split("/")[0]

        if config.input_type is None:
            raise ValueError("Missing mandatory config property: input_type")
        input_class = type_loader.get_type(config.input_type)

        output_class = Any
        if config.output_type is not None:
            output_class = type_loader.get_type(config.output_type)

        if config.description is not None:
            description = config.description
        else:
            description = f"{config.service_name} API"

        app.include_router(
            Routes.get_rest_routes(
                name=name,
                version=version,
                description=description,
                root_handler_name=root_handler,
                config=config,
                app_config=app_config,
                input_class=input_class,
                output_class=output_class,
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
                input_class=input_class,
            ),
            prefix=f"/{name}/{version}",
        )
