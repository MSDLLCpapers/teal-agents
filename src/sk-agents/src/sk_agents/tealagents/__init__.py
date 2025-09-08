# Top-level handler factory
from ska_utils import AppConfig

from sk_agents.ska_types import BaseConfig, BaseHandler
from sk_agents.tealagents.v1alpha1 import handle as tealagents_v1alpha1_handle


# need to be modified base on ticket CDW-917
def handle(
    config: BaseConfig,
    app_config: AppConfig,
    authorization: str | None = None
) -> BaseHandler:
    api, version = config.apiVersion.split("/")
    if api != "tealagents":
        raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

    match version:
        case "v1alpha1":
            return tealagents_v1alpha1_handle(
                config,
                app_config,
                authorization
            )
        case _:
            raise ValueError(f"Unknown apiVersion: {config.apiVersion}")
