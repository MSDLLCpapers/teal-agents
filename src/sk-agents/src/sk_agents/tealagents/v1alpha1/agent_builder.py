from typing import Any

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.functions.kernel_arguments import KernelArguments

from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.ska_types import ModelType
from sk_agents.tealagents.kernel_builder import KernelBuilder
from sk_agents.tealagents.v1alpha1.config import AgentConfig
from sk_agents.tealagents.v1alpha1.sk_agent import SKAgent
from sk_agents.type_loader import get_type_loader


class AgentBuilder:
    def __init__(self, kernel_builder: KernelBuilder, authorization: str | None = None):
        self.kernel_builder = kernel_builder
        self.authorization = authorization

    async def build_agent(
        self,
        agent_config: AgentConfig,
        extra_data_collector: ExtraDataCollector | None = None,
        output_type: str | None = None,
        user_id: str | None = None,
    ) -> SKAgent:
        kernel = await self.kernel_builder.build_kernel(
            agent_config.model,
            agent_config.name,
            agent_config.plugins,
            agent_config.remote_plugins,
            agent_config.mcp_servers,
            self.authorization,
            extra_data_collector,
            user_id,
        )

        so_supported: bool = self.kernel_builder.model_supports_structured_output(
            agent_config.model
        )

        settings = kernel.get_prompt_execution_settings_from_service_id(agent_config.name)
        settings.function_choice_behavior = FunctionChoiceBehavior.Auto(auto_invoke=False)
        extension_data = {}
        if agent_config.temperature:
            extension_data["temperature"] = float(agent_config.temperature)
        if agent_config.max_tokens:
            extension_data["max_tokens"] = int(agent_config.max_tokens)

        if extension_data:
            settings.extension_data = extension_data
            settings.unpack_extension_data()
        if so_supported and output_type:
            type_loader = get_type_loader()
            settings.response_format = type_loader.get_type(output_type)

        model_type: ModelType = self.kernel_builder.get_model_type_for_name(agent_config.model)

        model_attributes: dict[str, Any] = {
            "model_type": model_type,
            "so_supported": so_supported,
        }

        return SKAgent(
            model_name=agent_config.model,
            model_attributes=model_attributes,
            agent=ChatCompletionAgent(
                kernel=kernel,
                name=agent_config.name,
                instructions=agent_config.system_prompt,
                arguments=KernelArguments(settings=settings),
            ),
        )
