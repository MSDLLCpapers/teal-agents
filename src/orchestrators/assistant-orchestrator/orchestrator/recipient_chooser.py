import json
import logging

import requests
import requests.exceptions
from opentelemetry.propagate import inject
from pydantic import BaseModel, ConfigDict

from agents import RecipientChooserAgent, AgentConnectionError, AgentTimeoutError, AgentResponseError, AgentInvalidResponseError
from model import Conversation

logger = logging.getLogger(__name__)


class ReqAgent(BaseModel):
    name: str
    description: str


class RequestPayload(BaseModel):
    conversation_history: Conversation
    agent_list: list[ReqAgent]
    current_message: str


class SelectedAgent(BaseModel):
    agent_name: str
    confidence: str
    is_followup: bool


class ResponsePayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    output_raw: str


class RecipientChooser:
    """RecipientChooser

    Chooses which agent should handle the next message in a conversation.
    """

    def __init__(self, agent: RecipientChooserAgent):
        self.agent = agent
        self.agent_list: list[ReqAgent] = [
            ReqAgent(name=agent.name, description=agent.description)
            for agent in self.agent.agent_catalog.agents.values()
        ]

    @staticmethod
    def _clean_output(output: str) -> str:
        while output[0] != "{":
            output = output[1:]
            if len(output) < 2:
                raise Exception("Invalid response")
        while output[-1] != "}":
            output = output[:-1]
            if len(output) < 2:
                raise Exception("Invalid response")
        return output

    async def choose_recipient(
        self, message: str, conv: Conversation, authorization: str | None = None
    ) -> SelectedAgent:
        """Chooses the recipient

        Args:
            message (str): The current message from the client
            conv (Conversation): The conversation history, so far
        Returns:
            The name of the agent that should handle the message
        """
        payload: RequestPayload = RequestPayload(
            conversation_history=conv,
            agent_list=self.agent_list,
            current_message=message,
        )

        body_json = payload.model_dump_json()

        headers = {"taAgwKey": self.agent.api_key, "Authorization": authorization}
        inject(headers)

        try:
            raw_response = requests.post(
                self.agent.endpoint,
                headers=headers,
                data=body_json,
                timeout=120,
            )
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Agent selector '{self.agent.name}' is unreachable at {self.agent.endpoint}: {e}")
            raise AgentConnectionError(
                self.agent.name,
                f"Agent selector '{self.agent.name}' is not available at {self.agent.endpoint}. The service may be down or unreachable.",
            ) from e
        except requests.exceptions.Timeout as e:
            logger.error(f"Agent selector '{self.agent.name}' timed out: {e}")
            raise AgentTimeoutError(
                self.agent.name,
                f"Agent selector '{self.agent.name}' timed out while choosing a recipient.",
            ) from e
        except requests.exceptions.RequestException as e:
            logger.error(f"Request to agent selector '{self.agent.name}' failed: {e}")
            raise AgentConnectionError(
                self.agent.name,
                f"Failed to communicate with agent selector '{self.agent.name}': {e}",
            ) from e

        if raw_response.status_code != 200:
            detail = ""
            try:
                error_body = raw_response.json()
                detail = error_body.get("detail", raw_response.text)
            except Exception:
                detail = raw_response.text
            logger.error(f"Agent selector '{self.agent.name}' returned HTTP {raw_response.status_code}: {detail}")
            raise AgentResponseError(self.agent.name, raw_response.status_code, detail)

        try:
            response = raw_response.json()
        except Exception as e:
            logger.error(f"Agent selector '{self.agent.name}' returned invalid JSON: {e}")
            raise AgentInvalidResponseError(
                self.agent.name,
                f"Agent selector '{self.agent.name}' returned a response that could not be parsed.",
            ) from e

        if response:
            try:
                response_payload = ResponsePayload(**response)
                clean_json = RecipientChooser._clean_output(response_payload.output_raw)
                sel_agent: SelectedAgent = SelectedAgent(**json.loads(clean_json))
            except (json.JSONDecodeError, KeyError, Exception) as e:
                logger.error(f"Agent selector '{self.agent.name}' returned unparseable agent selection: {e}")
                raise AgentInvalidResponseError(
                    self.agent.name,
                    f"Agent selector '{self.agent.name}' returned a response that could not be parsed into an agent selection: {e}",
                ) from e
            return sel_agent
        else:
            raise Exception("Unable to determine recipient")
