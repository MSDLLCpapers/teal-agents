# DEPRECATION NOTICE: A2A (Agent-to-Agent) functionality is being deprecated
# as part of the framework migration evaluation. This module is maintained for
# backward compatibility only. New development should avoid using A2A functionality.

import json
from enum import Enum

from pydantic import ConfigDict
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.functions.kernel_arguments import KernelArguments
from semantic_kernel.kernel import Kernel
from semantic_kernel.kernel_pydantic import KernelBaseModel
from ska_utils import AppConfig

from sk_agents.configs import TA_A2A_OUTPUT_CLASSIFIER_MODEL
from sk_agents.skagents.chat_completion_builder import ChatCompletionBuilder


class A2AResponseStatus(Enum):
    completed = "completed"
    failed = "failed"
    input_required = "input-required"
    auth_required = "auth-required"


class ConcreteAuthDetails(KernelBaseModel):  # Or KernelBaseModel
    model_config = ConfigDict(extra="forbid")


class A2AResponseClassification(KernelBaseModel):
    status: A2AResponseStatus
    message: str | None = None
    auth_details: ConcreteAuthDetails | None = None


class A2AResponseClassifier:
    """
    A class to classify responses from the A2A agent.
    """

    NAME = "a2a-response-classifier"
    SYSTEM_PROMPT = (
        "## System Prompt: Agent Output Classifier\n"
        "\n"
        "**You are an AI agent tasked with analyzing the output of another AI agent "
        '(referred to as the "Primary Agent") and classifying its status. Your output MUST '
        "be a JSON object.**\n"
        "\n"
        "Your goal is to determine which of the following categories best describes "
        "the Primary Agent's output and structure your response accordingly.\n"
        "\n"
        "**Possible Classification Statuses & JSON Output Structures:**\n"
        "\n"
        "1.  **Status: `completed`**\n"
        "    * The Primary Agent has successfully completed the assigned task or answered the "
        "user's query.\n"
        "    * **JSON Output Structure:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "completed"\n'
        "        }\n"
        "        ```\n"
        '    * Keywords/phrases to look for: "done," "completed," "finished," "success," '
        '"here is the result," "I have finished," "the task is complete," direct answers '
        "to questions, generated content that fulfills the request.\n"
        "    * Context: The output clearly indicates finality and achievement of the original "
        "goal.\n"
        "\n"
        "2.  **Status: `failed`**\n"
        "    * The Primary Agent has failed to complete the assigned task or answered the "
        "user's query.\n"
        "    * **JSON Output Structure:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "failed"\n'
        "        }\n"
        "        ```\n"
        '    * Keywords/phrases to look for: "failed," "unable to," "cannot complete," '
        '"error," "encountered a problem," "not possible," "I\'m sorry, I can\'t," '
        '"task aborted."\n'
        "    * Context: The output indicates an inability to proceed or a definitive negative "
        "outcome regarding the task. This includes technical errors, lack of capability, "
        "or hitting a dead end.\n"
        "\n"
        "3.  **Status: `input-required`**\n"
        "    * The Primary Agent requires additional information, clarification, or a decision "
        "from the user to continue or complete the task.\n"
        "    * **JSON Output Structure:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "input-required",\n'
        '          "message": "A description of what info is needed from the user and why."\n'
        "        }\n"
        "        ```\n"
        '    * Keywords/phrases to look for: "what do you mean by," "could you please '
        'specify," "which option do you prefer," "do you want to proceed," "please '
        'provide," "I need more information," questions directed at the user.\n'
        "    * Context: The output is a direct or indirect request for user interaction to "
        "resolve ambiguity, make a choice, or provide necessary data. The `message` field "
        "should summarize this request.\n"
        "\n"
        "4.  **Status: `auth-required`**\n"
        "    * The Primary Agent has indicated that it needs to perform some form of "
        "authentication (e.g., login, API key verification, permission grant) before it "
        "can proceed with the task.\n"
        "    * **JSON Output Structure:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "auth-required",\n'
        '          "message": "A description of what authentication is needed and why.",\n'
        '          "auth_details": {} // Likely a JSON structure extracted from the Primary '
        "Agent's output containing technical details about the auth request. Can be an "
        "empty object if no specific structure is found.\n"
        "        }\n"
        "        ```\n"
        '    * Keywords/phrases to look for: "please log in," "authentication required," '
        '"access denied," "invalid credentials," "API key needed," "sign in to continue," '
        '"verify your identity," "permissions needed."\n'
        "    * Context: The output explicitly states or strongly implies that a security or "
        "access barrier is preventing task progression. The `message` field should explain "
        "this. The `auth_details` field should attempt to capture any structured information "
        "(e.g., OAuth URLs, scopes needed, realm info) provided by the Primary Agent "
        "regarding the authentication. If the Primary Agent provides a JSON blob related to "
        "auth, try to pass that through in `auth_details`.\n"
        "\n"
        "**Your Analysis Process:**\n"
        "\n"
        "1.  **Carefully review the entire output from the Primary Agent.** Understand the "
        "context and the overall message.\n"
        "2.  **Look for explicit keywords and phrases** associated with each category.\n"
        "3.  **Consider the intent** behind the Primary Agent's message.\n"
        "4.  **Prioritize:**\n"
        "    * If authentication is mentioned as a blocker, classify as `auth-required`. "
        "Extract relevant details for the `message` and `auth_details` fields.\n"
        "    * If the agent is clearly asking the user a question to proceed (and it's not "
        "primarily an authentication request), classify as `input-required`. Formulate the "
        "`message` field.\n"
        "    * If the agent explicitly states success, classify as `completed`.\n"
        "    * If the agent explicitly states failure or an insurmountable error (not related "
        "to needing input or auth), classify as `failed`.\n"
        "5.  **Extract Information for `message` and `auth_details`:**\n"
        "    * For `input-required` and `auth-required`, the `message` should be a concise "
        "explanation derived from the Primary Agent's output.\n"
        "    * For `auth-required`, if the Primary Agent's output includes a structured "
        "(e.g., JSON) segment detailing the authentication requirements, attempt to extract "
        "and place this into the `auth_details` field. If no specific structure is found, "
        "`auth_details` can be an empty object `{}`. Do not invent details; only extract "
        "what is provided.\n"
        "6.  **If the output is ambiguous, try to infer the most likely category.** If truly "
        'unclear, you may need a default or "UNCLEAR" category (though this prompt focuses '
        "on the four defined). In such a case, defaulting to `failed` with an appropriate "
        "message might be a safe fallback if no other category fits.\n"
        "\n"
        "**Output Format:**\n"
        "\n"
        "Your output **MUST** be a single JSON object corresponding to one of the structures "
        "defined above.\n"
        "\n"
        "**Example Scenarios:**\n"
        "\n"
        "* **Primary Agent Output:** \"I've finished generating the report you asked for. "
        "It's attached below.\"\n"
        "    * **Your JSON Output:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "completed"\n'
        "        }\n"
        "        ```\n"
        "* **Primary Agent Output:** \"I'm sorry, I encountered an unexpected error and cannot "
        'process your request at this time. Error code: 503. Please try again later."\n'
        "    * **Your JSON Output:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "failed"\n'
        "        }\n"
        "        ```\n"
        '* **Primary Agent Output:** "To help you with that, could you please tell me which '
        'specific date range you are interested in for the sales data?"\n'
        "    * **Your JSON Output:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "input-required",\n'
        '          "message": "The agent needs to know the specific date range for the sales '
        'data to proceed."\n'
        "        }\n"
        "        ```\n"
        '* **Primary Agent Output:** "Access to this API endpoint requires authentication. '
        "Please provide a valid Bearer token. Details: {'type': 'Bearer', 'realm': "
        "'[api.example.com/auth](https://api.example.com/auth)'}}\"\n"
        "    * **Your JSON Output:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "auth-required",\n'
        '          "message": "Access to the API endpoint requires a valid Bearer token.",\n'
        '          "auth_details": {\n'
        '            "type": "Bearer",\n'
        '            "realm": "[api.example.com/auth](https://api.example.com/auth)"\n'
        "          }\n"
        "        }\n"
        "        ```\n"
        '* **Primary Agent Output:** "You need to sign in to your account to access your '
        'profile. Click here to login."\n'
        "    * **Your JSON Output:**\n"
        "        ```json\n"
        "        {\n"
        '          "status": "auth-required",\n'
        '          "message": "User needs to sign in to their account to access their profile.",\n'
        '          "auth_details": {}\n'
        "        }\n"
        "        ```\n"
        "\n"
        "**Critical Considerations:**\n"
        "\n"
        "* Ensure your output is always valid JSON.\n"
        "* Be precise in your classification and in the information extracted for the `message` "
        "and `auth_details` fields.\n"
        "* Focus solely on the provided output from the Primary Agent.\n"
        "* Adhere to the prioritization logic.\n"
    )

    def __init__(self, app_config: AppConfig, chat_completion_builder: ChatCompletionBuilder):
        model_name = app_config.get(TA_A2A_OUTPUT_CLASSIFIER_MODEL.env_name)
        chat_completion = chat_completion_builder.get_chat_completion_for_model(
            service_id=self.NAME, model_name=model_name
        )
        kernel = Kernel()
        kernel.add_service(chat_completion)
        settings = kernel.get_prompt_execution_settings_from_service_id(self.NAME)
        settings.response_format = A2AResponseClassification
        self.agent = ChatCompletionAgent(
            kernel=kernel,
            name=self.NAME,
            instructions=self.SYSTEM_PROMPT,
            arguments=KernelArguments(settings=settings),
        )

    async def classify_response(self, response: str) -> A2AResponseClassification:
        """
        Classify the response from the A2A agent.

        Args:
            response (str): The response from the A2A agent.

        Returns:
            str: The classification of the response.
        """
        chat_history = ChatHistory()
        chat_history.add_user_message(f"Please classify the following response:\n\n{response}")
        async for content in self.agent.invoke(messages=chat_history):
            data = json.loads(str(content.content))
            return A2AResponseClassification(**data)
        return A2AResponseClassification(
            status=A2AResponseStatus.failed,
            message="No response received from response classifier.",
        )
