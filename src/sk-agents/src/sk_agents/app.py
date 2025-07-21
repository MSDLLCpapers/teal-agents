import logging
from enum import Enum

from fastapi import FastAPI
from pydantic_yaml import parse_yaml_file_as
from ska_utils import AppConfig, get_telemetry, initialize_telemetry

from sk_agents.appv1 import AppV1
from sk_agents.appv2 import AppV2
from sk_agents.appv3 import AppV3
from sk_agents.configs import (
    TA_SERVICE_CONFIG,
    configs,
)
from sk_agents.middleware import TelemetryMiddleware
from sk_agents.ska_types import (
    BaseConfig,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AppVersion(Enum):
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"


try:
    AppConfig.add_configs(configs)
    app_config = AppConfig()

    config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
    if not config_file:
        raise FileNotFoundError(f"Configuration file not found for {TA_SERVICE_CONFIG.env_name}")
    try:
        config: BaseConfig = parse_yaml_file_as(BaseConfig, config_file)
    except Exception as e:
        logger.exception(f"Failed to parse YAML configuration. -{e}")
        raise

    try:
        (root_handler, api_version) = config.apiVersion.split("/")
    except ValueError:
        logger.exception("Invalid API version format")
        raise

    name: str | None = None
    version = str(config.version)
    app_version: str | None = None

    if root_handler == "tealagents":
        if api_version == "v1alpha1":
            app_version = AppVersion.V3
            name = config.name
    elif root_handler == "skagents":
        if api_version == "v2alpha1":
            app_version = AppVersion.V2
            name = config.name
        else:
            app_version = AppVersion.V1
            name = config.service_name

    if not app_version:
        raise ValueError("Invalid apiVersion defined in the configuration file.")
    if not name:
        raise ValueError("Service name is not defined in the configuration file.")
    if not version:
        raise ValueError("Service version is not defined in the configuration file.")

    initialize_telemetry(f"{name}-{version}", app_config)

    app = FastAPI(
        openapi_url=f"/{name}/{version}/openapi.json",
        docs_url=f"/{name}/{version}/docs",
        redoc_url=f"/{name}/{version}/redoc",
    )
    # noinspection PyTypeChecker
    app.add_middleware(TelemetryMiddleware, st=get_telemetry())

    match app_version:
        case AppVersion.V1:
            AppV1.run(name, version, app_config, config, app)
        case AppVersion.V2:
            AppV2.run(name, version, app_config, config, app)
        case AppVersion.V3:
            AppV3.run(name, version, app_config, config, app)

except Exception as e:
    logger.exception(f"Application failed to start due to an error. -{e}")
    raise
