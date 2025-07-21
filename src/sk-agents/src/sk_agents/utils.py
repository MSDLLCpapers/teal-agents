import logging
import os

from ska_utils import AppConfig

from sk_agents.configs import TA_PLUGIN_MODULE
from sk_agents.plugin_loader import get_plugin_loader
from sk_agents.ska_types import (
    IntermediateTaskResponse,
    InvokeResponse,
    PartialResponse,
)

logger = logging.getLogger(__name__)


def docstring_parameter(*sub):
    def dec(obj):
        obj.__doc__ = obj.__doc__.format(*sub)
        return obj

    return dec


def initialize_plugin_loader(agents_path: str, app_config: AppConfig):
    try:
        plugin_module = app_config.get(TA_PLUGIN_MODULE.env_name)
        # If no plugin module has been defined:
        # Check if there is a custom_plugins.py file in the agents directory
        if plugin_module is None:
            custom_plugins = os.path.join(agents_path, "custom_plugins.py")
            if os.path.exists(custom_plugins):
                app_config.props[TA_PLUGIN_MODULE.env_name] = custom_plugins
                plugin_module = custom_plugins
        get_plugin_loader(plugin_module)
    except Exception as e:
        logger.exception(f"Failed to initialize plugin loader: {e}")
        raise


def get_sse_event_for_response(
    response: IntermediateTaskResponse | PartialResponse | InvokeResponse,
) -> str:
    try:
        if isinstance(response, IntermediateTaskResponse):
            return f"event: intermediate-task-response\ndata: {response.model_dump_json()}\n\n"
        elif isinstance(response, PartialResponse):
            return f"event: partial-response\ndata: {response.model_dump_json()}\n\n"
        elif isinstance(response, InvokeResponse):
            return f"event: final-response\ndata: {response.model_dump_json()}\n\n"
        else:
            return f"event: unknown\ndata: {str(response)}\n\n"
    except Exception as e:
        logger.exception("Failed to serialize SSE event for response")
        return f'event: error\ndata: {{"error": "{str(e)}"}}\n\n'
