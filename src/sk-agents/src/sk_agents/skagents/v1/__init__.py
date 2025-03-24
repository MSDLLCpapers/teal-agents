from ska_utils import AppConfig

from sk_agents.ska_types import BaseHandler, Config
from sk_agents.skagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.skagents.kernel_builder import KernelBuilder
from sk_agents.skagents.remote_plugin_loader import (
    RemotePluginLoader,
    RemotePluginCatalog,
)
from sk_agents.skagents.v1.sequential.agent_builder import AgentBuilder
from sk_agents.skagents.v1.sequential.sequential_skagents import SequentialSkagents
from sk_agents.skagents.v1.sequential.task_builder import TaskBuilder


def handle(config: Config, app_config: AppConfig, authorization: str | None = None):
    if config.apiVersion != "skagents/v1":
        raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

    match config.kind:
        case "Sequential":
            return _handle_sequential(config, app_config, authorization)
        case _:
            raise ValueError(f"Unknown kind: {config.kind}")


def _handle_sequential(
    config: Config, app_config: AppConfig, authorization: str | None = None
) -> BaseHandler:
    remote_plugin_loader = RemotePluginLoader(RemotePluginCatalog(app_config))
    chat_completion_builder = ChatCompletionBuilder(app_config)
    kernel_builder = KernelBuilder(
        chat_completion_builder, remote_plugin_loader, app_config
    )
    agent_builder = AgentBuilder(kernel_builder)
    task_builder = TaskBuilder(agent_builder, authorization)
    seq_skagents = SequentialSkagents(config, kernel_builder, task_builder)
    return seq_skagents
