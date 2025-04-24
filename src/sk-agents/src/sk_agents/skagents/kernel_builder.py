from semantic_kernel.kernel import Kernel
from ska_utils import AppConfig

from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.plugin_loader import get_plugin_loader
from sk_agents.ska_types import ModelType
from sk_agents.skagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.skagents.remote_plugin_loader import RemotePluginLoader


class KernelBuilder:
    def __init__(
        self,
        chat_completion_builder: ChatCompletionBuilder,
        remote_plugin_loader: RemotePluginLoader,
        app_config: AppConfig,
        authorization: str | None = None,
    ):
        self.chat_completion_builder: ChatCompletionBuilder = chat_completion_builder
        self.remote_plugin_loader = remote_plugin_loader
        self.app_config: AppConfig = app_config
        self.authorization = authorization

    def build_kernel(
        self,
        model_name: str,
        service_id: str,
        plugins: list[str],
        remote_plugins: list[str],
        authorization: str | None = None,
        extra_data_collector: ExtraDataCollector | None = None,
    ) -> Kernel:
        kernel = self._create_base_kernel(model_name, service_id)
        kernel = self._parse_plugins(plugins, kernel, authorization, extra_data_collector)
        return self._load_remote_plugins(remote_plugins, kernel)

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        return self.chat_completion_builder.get_model_type_for_name(model_name)

    def model_supports_structured_output(self, model_name: str) -> bool:
        return self.chat_completion_builder.model_supports_structured_output(model_name)

    def _create_base_kernel(self, model_name: str, service_id: str) -> Kernel:
        chat_completion = self.chat_completion_builder.get_chat_completion_for_model(
            service_id=service_id,
            model_name=model_name,
        )

        kernel = Kernel()
        kernel.add_service(chat_completion)

        return kernel

    def _load_remote_plugins(self, remote_plugins: list[str], kernel: Kernel) -> Kernel:
        if remote_plugins is None or len(remote_plugins) < 1:
            return kernel
        self.remote_plugin_loader.load_remote_plugins(kernel, remote_plugins)
        return kernel

    @staticmethod
    def _parse_plugins(
        plugin_names: list[str],
        kernel: Kernel,
        authorization: str | None = None,
        extra_data_collector: ExtraDataCollector | None = None,
    ) -> Kernel:
        if plugin_names is None or len(plugin_names) < 1:
            return kernel

        plugin_loader = get_plugin_loader()
        plugins = plugin_loader.get_plugins(plugin_names)
        for k, v in plugins.items():
            kernel.add_plugin(v(authorization, extra_data_collector), k)
        return kernel
