from ska_utils import AppConfig

from sk_agents.ska_types import BaseConfig, BaseHandler
from sk_agents.skagents.v1 import handle as skagents_v1_handle


def handle(
    config: BaseConfig, app_config: AppConfig, authorization: str | None = None
) -> BaseHandler:
    api, version = config.apiVersion.split("/")
    if api != "skagents":
        raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

    match version:
        case "v1" | "v2alpha1":
            return skagents_v1_handle(config, app_config, authorization)
        case _:
            raise ValueError(f"Unknown apiVersion: {config.apiVersion}")
