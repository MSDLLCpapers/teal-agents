import logging

from semantic_kernel.kernel import Kernel
from ska_utils import AppConfig

from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.secure_auth_storage_manager import SecureAuthStorageManager
from sk_agents.authorization.authorizer_factory import AuthorizerFactory
from sk_agents.authorization.request_authorizer import RequestAuthorizer
from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.plugin_loader import get_plugin_loader
from sk_agents.ska_types import ModelType
from sk_agents.tealagents.chat_completion_builder import ChatCompletionBuilder
from sk_agents.tealagents.remote_plugin_loader import RemotePluginLoader


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
        self.logger = logging.getLogger(__name__)

        # Initialize auth storage and authorizer for token cache functionality
        self.auth_storage_manager: SecureAuthStorageManager = AuthStorageFactory(
            app_config
        ).get_auth_storage_manager()
        self.authorizer: RequestAuthorizer = AuthorizerFactory(app_config).get_authorizer()

    async def build_kernel(
        self,
        model_name: str,
        service_id: str,
        plugins: list[str],
        remote_plugins: list[str],
        authorization: str | None = None,
        extra_data_collector: ExtraDataCollector | None = None,
    ) -> Kernel:
        try:
            kernel = self._create_base_kernel(model_name, service_id)
            kernel = await self._parse_plugins(plugins, kernel, authorization, extra_data_collector)
            return self._load_remote_plugins(remote_plugins, kernel)
        except Exception as e:
            self.logger.exception(f"Could build kernel with service ID {service_id}. - {e}")
            raise

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        try:
            return self.chat_completion_builder.get_model_type_for_name(model_name)
        except Exception as e:
            self.logger.exception(f"Could not get model type for {model_name}. - {e}")
            raise

    def model_supports_structured_output(self, model_name: str) -> bool:
        return self.chat_completion_builder.model_supports_structured_output(model_name)

    def _create_base_kernel(self, model_name: str, service_id: str) -> Kernel:
        try:
            chat_completion = self.chat_completion_builder.get_chat_completion_for_model(
                service_id=service_id,
                model_name=model_name,
            )

            kernel = Kernel()
            kernel.add_service(chat_completion)

            return kernel
        except Exception as e:
            self.logger.exception(f"Could not create base kernelwith service id {service_id}.-{e}")
            raise

    def _load_remote_plugins(self, remote_plugins: list[str], kernel: Kernel) -> Kernel:
        if remote_plugins is None or len(remote_plugins) < 1:
            return kernel
        try:
            self.remote_plugin_loader.load_remote_plugins(kernel, remote_plugins)
            return kernel
        except Exception as e:
            self.logger.exception(f"Could not load remote plugings. -{e}")
            raise

    async def _parse_plugins(
        self,
        plugin_names: list[str],
        kernel: Kernel,
        authorization: str | None = None,
        extra_data_collector: ExtraDataCollector | None = None,
    ) -> Kernel:
        if plugin_names is None or len(plugin_names) < 1:
            return kernel

        plugin_loader = get_plugin_loader()
        plugins = plugin_loader.get_plugins(plugin_names)

        for plugin_name, plugin_class in plugins.items():
            # Get plugin-specific authorization (with token cache if available)
            plugin_authorization = await self._get_plugin_authorization(plugin_name, authorization)

            # Create and add the plugin to the kernel
            kernel.add_plugin(plugin_class(plugin_authorization, extra_data_collector), plugin_name)

        return kernel

    async def _get_plugin_authorization(
        self, plugin_name: str, original_authorization: str | None = None
    ) -> str | None:
        """
        Get plugin-specific authorization, checking token cache for stored OAuth2 tokens.

        Args:
            plugin_name: Name of the plugin requesting authorization
            original_authorization: Original authorization header from the request

        Returns:
            Authorization string to use for the plugin (either cached token or original)
        """
        if not original_authorization:
            return None

        try:
            # Extract user ID from the authorization header
            user_id = await self.authorizer.authorize_request(original_authorization)
            if not user_id:
                self.logger.warning(
                    f"Could not extract user ID from authorization for plugin {plugin_name}"
                )
                return original_authorization

            # Try to retrieve cached OAuth2 tokens for this user and plugin
            cached_auth_data = self.auth_storage_manager.retrieve(user_id, plugin_name)

            if cached_auth_data and hasattr(cached_auth_data, "access_token"):
                self.logger.info(f"Using cached token for plugin {plugin_name}, user {user_id}")
                # Return the cached access token in Bearer format
                return f"Bearer {cached_auth_data.access_token}"
            else:
                self.logger.debug(
                    f"No cached tokens found for plugin {plugin_name}, user {user_id} - "
                    f"returning None"
                )
                return None

        except Exception as e:
            self.logger.warning(
                f"Error retrieving cached tokens for plugin {plugin_name}: {e} - returning None"
            )
            return None
