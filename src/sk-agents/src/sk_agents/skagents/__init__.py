from ska_utils import AppConfig

from sk_agents.ska_types import BaseHandler, Config
from sk_agents.skagents.v1 import handle as skagents_v1_handle


def handle(config: Config, app_config: AppConfig, authorization: str | None = None) -> BaseHandler:
    api, version = config.apiVersion.split("/")
    if api != "skagents":
        raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

    match version:
        case "v1":
            return skagents_v1_handle(config, app_config, authorization)
        case _:
            raise ValueError(f"Unknown apiVersion: {config.apiVersion}")
