from ska_utils import AppConfig

from sk_agents.ska_types import (
    BaseConfig,
    BaseHandler,
)
from sk_agents.skagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.skagents.kernel_builder import KernelBuilder
from sk_agents.skagents.remote_plugin_loader import (
    RemotePluginCatalog,
    RemotePluginLoader,
)
from sk_agents.skagents.v1.agent_builder import AgentBuilder
from sk_agents.skagents.v1.chat.chat_agents import ChatAgents
from sk_agents.skagents.v1.sequential.sequential_skagents import SequentialSkagents
from sk_agents.skagents.v1.sequential.task_builder import TaskBuilder


def handle(config: BaseConfig, app_config: AppConfig, authorization: str | None = None):
    if config.apiVersion != "skagents/v1":
        raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

    match config.kind:
        case "Sequential":
            return _handle_sequential(config, app_config, authorization)
        case "Chat":
            return _handle_chat(config, app_config, authorization)
        case _:
            raise ValueError(f"Unknown kind: {config.kind}")


def _handle_chat(
    config: BaseConfig, app_config: AppConfig, authorization: str | None = None
) -> BaseHandler:
    remote_plugin_loader = RemotePluginLoader(RemotePluginCatalog(app_config))
    chat_completion_builder = ChatCompletionBuilder(app_config)
    kernel_builder = KernelBuilder(chat_completion_builder, remote_plugin_loader, app_config)
    agent_builder = AgentBuilder(kernel_builder, authorization)
    chat_agents = ChatAgents(config, agent_builder)
    return chat_agents


def _handle_sequential(
    config: BaseConfig, app_config: AppConfig, authorization: str | None = None
) -> BaseHandler:
    remote_plugin_loader = RemotePluginLoader(RemotePluginCatalog(app_config))
    chat_completion_builder = ChatCompletionBuilder(app_config)
    kernel_builder = KernelBuilder(chat_completion_builder, remote_plugin_loader, app_config)
    agent_builder = AgentBuilder(kernel_builder, authorization)
    task_builder = TaskBuilder(agent_builder)
    seq_skagents = SequentialSkagents(config, kernel_builder, task_builder)
    return seq_skagents
