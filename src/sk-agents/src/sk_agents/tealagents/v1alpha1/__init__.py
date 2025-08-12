from ska_utils import AppConfig

from sk_agents.ska_types import (
    BaseConfig,
    BaseHandler,
)
from sk_agents.tealagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.tealagents.kernel_builder import KernelBuilder
from sk_agents.tealagents.remote_plugin_loader import (
    RemotePluginCatalog,
    RemotePluginLoader,
)
from sk_agents.tealagents.v1alpha1.agent_builder import AgentBuilder


def handle(config: BaseConfig, app_config: AppConfig, authorization: str | None = None):
    if config.apiVersion != "tealagents/v1alpha1":
        raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

    match config.kind:
        # need to be modified base on ticket CDW-917
        case "agent":
            return _handle_chat(config, app_config, authorization, False)
        case _:
            raise ValueError(f"Unknown kind: {config.kind}")


# need to be modified base on ticket CDW-917
def _handle_chat(
    config: BaseConfig,
    app_config: AppConfig,
    authorization: str | None = None,
) -> BaseHandler:
    from sk_agents.tealagents.v1alpha1.agent.handler import TealAgentsV1Alpha1Handler

    remote_plugin_loader = RemotePluginLoader(RemotePluginCatalog(app_config))
    chat_completion_builder = ChatCompletionBuilder(app_config)
    kernel_builder = KernelBuilder(chat_completion_builder, remote_plugin_loader, app_config)
    agent_builder = AgentBuilder(kernel_builder, authorization)
    chat_agents = TealAgentsV1Alpha1Handler(config, agent_builder)
    return chat_agents
 