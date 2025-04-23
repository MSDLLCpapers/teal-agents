from typing import Dict
import json
import requests
from opentelemetry.propagate import inject
from pydantic import BaseModel

from model import Conversation, ContextItem, ContextType
from services.services_client import (
    ServicesClient,
    MessageType,
    GeneralResponse,
    VerifyTicketResponse,
)


class NewConversationRequest(BaseModel):
    user_id: str
    is_resumed: bool | None = None


class GetConversationRequest(BaseModel):
    user_id: str
    session_id: str


class AddConversationMessageRequest(BaseModel):
    message_type: MessageType
    agent_name: str
    message: str


class VerifyTicketRequest(BaseModel):
    ticket: str
    ip_address: str


class AddContextRequest(BaseModel):
    item_key: str
    item_value: str


class UpdateContextRequest(BaseModel):
    item_value: str


class ExternalServicesClient(ServicesClient):
    def __init__(self, orchestrator_name: str, endpoint: str, token: str | None = None):
        self.orchestrator_name = orchestrator_name
        self.endpoint = endpoint
        self.token = token

    def new_conversation(self, user_id: str, is_resumed: bool) -> Conversation:
        request = NewConversationRequest(user_id=user_id, is_resumed=is_resumed)

        headers = {
            "taAgwKey": self.token,
        }
        inject(headers)
        try:
            history_response = requests.post(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/conversation-history",
                headers=headers,
                data=request.model_dump_json(),
            )
            history_response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text['detail'])}")
        history_response = history_response.json()
        user_context_response = self.get_context_items(user_id)
        user_context: Dict[str, ContextItem] = {}
        for key, value in user_context_response.items():
            user_context[key] = ContextItem(
                value=value, context_type=ContextType.PERSISTENT
            )

        return Conversation(
            **history_response, user_id=user_id, user_context=user_context
        )

    def get_conversation(self, user_id: str, session_id: str) -> Conversation:
        request = GetConversationRequest(user_id=user_id, session_id=session_id)
        headers = {
            "taAgwKey": self.token,
        }
        inject(headers)
        try:
            history_response = requests.get(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/conversation-history/{session_id}",
                headers=headers,
                data=request.model_dump_json(),
            )
            history_response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text)['detail']}")
        history_response = history_response.json()
        user_context_response = self.get_context_items(user_id)
        user_context: Dict[str, ContextItem] = {}
        for key, value in user_context_response.items():
            user_context[key] = ContextItem(
                value=value, context_type=ContextType.PERSISTENT
            )
        return Conversation(
            **history_response, user_id=user_id, user_context=user_context
        )

    def add_conversation_message(
        self,
        conversation_id: str,
        message_type: MessageType,
        agent_name: str,
        message: str,
    ) -> GeneralResponse:
        request = AddConversationMessageRequest(
            message_type=message_type, agent_name=agent_name, message=message
        )

        headers = {
            "taAgwKey": self.token,
        }
        inject(headers)
        try:
            response = requests.post(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/conversation-history/{conversation_id}/messages",
                headers=headers,
                data=request.model_dump_json(),
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text)['detail']}")
        response = response.json()
        return GeneralResponse(**response)


    def verify_ticket(self, ticket: str, ip_address: str) -> VerifyTicketResponse:
        request = VerifyTicketRequest(ticket=ticket, ip_address=ip_address)

        headers = {
            "taAgwKey": self.token,
        }
        inject(headers)
        try:
            response = requests.post(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/tickets/verify",
                headers=headers,
                data=request.model_dump_json(),
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text)['detail']}")
        response = response.json()
        return VerifyTicketResponse(**response)


    def add_context_item(
        self, user_id: str, item_key: str, item_value: str
    ) -> GeneralResponse:
        request = AddContextRequest(item_key=item_key, item_value=item_value)

        headers = {
            "taAgwKey": self.token,
        }
        inject(headers)
        try:
            response = requests.post(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/users/{user_id}/context",
                headers=headers,
                data=request.model_dump_json(),
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text)['detail']}")
        response = response.json()
        return GeneralResponse(**response)


    def update_context_item(
        self, user_id: str, item_key: str, item_value: str
    ) -> GeneralResponse:
        request = UpdateContextRequest(item_value=item_value)

        headers = {
            "taAgwKey": self.token,
        }
        inject(headers)
        try:
            response = requests.put(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/users/{user_id}/context/{item_key}",
                headers=headers,
                data=request.model_dump_json(),
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text)['detail']}")
        response = response.json()
        return GeneralResponse(**response)


    def delete_context_item(self, user_id: str, item_key: str) -> GeneralResponse:
        headers = {
            "taAgwKey": self.token,
        }
        inject(headers)
        try:
            response = requests.delete(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/users/{user_id}/context/{item_key}",
                headers=headers,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text)['detail']}")
        response = response.json()
        return GeneralResponse(**response)


    def get_context_items(self, user_id: str) -> Dict[str, str]:
        headers = {
            "taAgwKey": self.token,
        }
        inject(headers)
        try:
            response = requests.get(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/users/{user_id}/context",
                headers=headers,
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text)['detail']}")
        response = response.json()
        return response

