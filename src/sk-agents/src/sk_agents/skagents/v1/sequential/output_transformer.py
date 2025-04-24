import json

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.functions.kernel_arguments import KernelArguments
from ska_utils import AppConfig

from sk_agents.configs import TA_STRUCTURED_OUTPUT_TRANSFORMER_MODEL
from sk_agents.ska_types import InvokeResponse, TokenUsage
from sk_agents.skagents.kernel_builder import KernelBuilder
from sk_agents.type_loader import get_type_loader


class OutputTransformer:
    NAME = "structured-output"
    SYSTEM_PROMPT = (
        "Convert the given text into a structured output. Do not summarize or paraphrase the text."
    )

    def __init__(self, kernel_builder: KernelBuilder):
        self.kernel_builder = kernel_builder

    async def transform_output(self, output: str, output_type_str: str) -> InvokeResponse:
        type_loader = get_type_loader()
        output_type = type_loader.get_type(output_type_str)

        app_config = AppConfig()
        structured_output_model = app_config.get(TA_STRUCTURED_OUTPUT_TRANSFORMER_MODEL.env_name)

        kernel = self.kernel_builder.build_kernel(
            model_name=structured_output_model,
            service_id=self.NAME,
            plugins=[],
            remote_plugins=[],
        )

        settings = kernel.get_prompt_execution_settings_from_service_id(self.NAME)
        settings.function_choice_behavior = FunctionChoiceBehavior.Auto()
        settings.response_format = output_type

        agent = ChatCompletionAgent(
            kernel=kernel,
            name=self.NAME,
            instructions=self.SYSTEM_PROMPT,
            arguments=KernelArguments(settings=settings),
        )

        history = ChatHistory()
        history.add_user_message(output)

        async for content in agent.invoke(history):
            data = json.loads(content.content)
            return InvokeResponse(
                token_usage=TokenUsage(
                    completion_tokens=content.inner_content.usage.completion_tokens,
                    prompt_tokens=content.inner_content.usage.prompt_tokens,
                    total_tokens=(
                        content.inner_content.usage.completion_tokens
                        + content.inner_content.usage.prompt_tokens
                    ),
                ),
                output_raw=output,
                output_pydantic=output_type(**data),
            )
