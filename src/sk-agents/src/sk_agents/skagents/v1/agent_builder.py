from typing import Any

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.functions.kernel_arguments import KernelArguments

from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.ska_types import ModelType
from sk_agents.skagents.kernel_builder import KernelBuilder
from sk_agents.skagents.v1.sequential.config import AgentConfig
from sk_agents.skagents.v1.sk_agent import SKAgent
from sk_agents.type_loader import get_type_loader


class AgentBuilder:
    def __init__(self, kernel_builder: KernelBuilder, authorization: str | None = None):
        self.kernel_builder = kernel_builder
        self.authorization = authorization

    def build_agent(
        self,
        agent_config: AgentConfig,
        extra_data_collector: ExtraDataCollector | None = None,
        output_type: str | None = None,
    ) -> SKAgent:
        kernel = self.kernel_builder.build_kernel(
            agent_config.model,
            agent_config.name,
            agent_config.plugins,
            agent_config.remote_plugins,
            self.authorization,
            extra_data_collector,
        )

        so_supported: bool = self.kernel_builder.model_supports_structured_output(
            agent_config.model
        )

        settings = kernel.get_prompt_execution_settings_from_service_id(agent_config.name)
        settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
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
