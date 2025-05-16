import json

import aiohttp
from opentelemetry.propagate import inject
from pydantic import BaseModel, ConfigDict

from agents import RecipientChooserAgent
from model import Conversation


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

    async def choose_recipient(self, message: str, conv: Conversation) -> SelectedAgent:
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

        headers = {
            "taAgwKey": self.agent.api_key,
        }
        inject(headers)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.agent.endpoint,
                headers=headers,
                data=body_json,
            ) as response:
                if response.status == 200:
                    response_json = await response.json()
                    response_payload = ResponsePayload(**response_json)
                    clean_json = RecipientChooser._clean_output(response_payload.output_raw)
                    sel_agent: SelectedAgent = SelectedAgent(**json.loads(clean_json))
                    return sel_agent
                else:
                    raise Exception("Unable to determine recipient")
