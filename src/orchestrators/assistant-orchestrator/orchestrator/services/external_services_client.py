import json

import aiohttp
import requests
from opentelemetry.propagate import inject
from pydantic import BaseModel

from model import ContextItem, ContextType, Conversation
from services.services_client import (
    GeneralResponse,
    MessageType,
    ServicesClient,
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
        self.headers = {
            "taAgwKey": self.token,
        }

    async def new_conversation(self, user_id: str, is_resumed: bool) -> Conversation:
        conv_request = NewConversationRequest(user_id=user_id, is_resumed=is_resumed)
        inject(self.headers)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/conversation-history",
                    headers=self.headers,
                    data=conv_request.model_dump_json(),
                ) as response:
                    if response.status != 200:
                        error_detail = await response.text()
                        raise Exception(f"ERROR: {json.loads(error_detail)['detail']}")
                    history_response = await response.json()
            except aiohttp.ClientError as e:
                raise Exception(f"HTTP request failed: {str(e)}") from e

        user_context_response = await self.get_context_items(user_id)
        user_context: dict[str, ContextItem] = {}
        for key, value in user_context_response.items():
            user_context[key] = ContextItem(value=value, context_type=ContextType.PERSISTENT)
        return Conversation(**history_response, user_id=user_id, user_context=user_context)

    async def get_conversation(self, user_id: str, session_id: str) -> Conversation:
        conv_request = GetConversationRequest(user_id=user_id, session_id=session_id)
        inject(self.headers)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/conversation-history/{session_id}",
                    headers=self.headers,
                    data=conv_request.model_dump_json(),
                ) as response:
                    if response.status != 200:
                        error_detail = await response.text()
                        raise Exception(f"ERROR: {json.loads(error_detail)['detail']}")
                    history_response = await response.json()
        except aiohttp.ClientError as e:
            raise Exception(f"HTTP request failed: {str(e)}") from e

        user_context_response = await self.get_context_items(user_id)
        user_context: dict[str, ContextItem] = {}
        for key, value in user_context_response.items():
            user_context[key] = ContextItem(value=value, context_type=ContextType.PERSISTENT)

        return Conversation(**history_response, user_id=user_id, user_context=user_context)

    async def add_conversation_message(
        self,
        conversation_id: str,
        message_type: MessageType,
        agent_name: str,
        message: str,
    ) -> GeneralResponse:
        request = AddConversationMessageRequest(
            message_type=message_type, agent_name=agent_name, message=message
        )

        inject(self.headers)
        url = (
            f"{self.endpoint}/services/v1/{self.orchestrator_name}"
            f"/conversation-history/{conversation_id}/messages"
        )

        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url=url,
                    headers=self.headers,
                    data=request.model_dump_json(),
                ) as response:
                    if response.status != 200:
                        error_detail = await response.text()
                        raise Exception(f"ERROR: {json.loads(error_detail)['detail']}")
                    response_data = await response.json()
            except aiohttp.ClientError as e:
                raise Exception(f"HTTP Client Error: {str(e)}") from e

        return GeneralResponse(**response_data)

    async def verify_ticket(self, ticket: str, ip_address: str) -> VerifyTicketResponse:
        ticket_request = VerifyTicketRequest(ticket=ticket, ip_address=ip_address)

        inject(self.headers)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(
                    url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/tickets/verify",
                    headers=self.headers,
                    data=ticket_request.model_dump_json(),
                ) as response:
                    if response.status != 200:
                        error_detail = await response.text()
                        raise Exception(f"ERROR: {json.loads(error_detail)['detail']}")
                    response_data = await response.json()
            except aiohttp.ClientError as e:
                raise Exception(f"HTTP Client Error: {str(e)}") from e

        return VerifyTicketResponse(**response_data)

    async def add_context_item(
        self, user_id: str, item_key: str, item_value: str | None
    ) -> GeneralResponse:
        context_request = AddContextRequest(item_key=item_key, item_value=item_value)

        inject(self.headers)
        try:
            response = requests.post(
                url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/users/{user_id}/context",
                headers=self.headers,
                data=context_request.model_dump_json(),
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            raise Exception(f"ERROR: {json.loads(e.response.text)['detail']}") from e
        response = response.json()
        return GeneralResponse(**response)

    async def update_context_item(
        self, user_id: str, item_key: str, item_value: str | None
    ) -> GeneralResponse:
        context_request = UpdateContextRequest(item_value=item_value)

        inject(self.headers)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.put(
                    url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/users/{user_id}/context/{item_key}",
                    headers=self.headers,
                    data=context_request.model_dump_json(),
                ) as response:
                    if response.status != 200:
                        error_detail = await response.text()
                        raise Exception(f"ERROR: {json.loads(error_detail)['detail']}")
                    response_data = await response.json()
            except aiohttp.ClientError as e:
                raise Exception(f"HTTP Client Error: {str(e)}") from e

        return GeneralResponse(**response_data)

    async def delete_context_item(self, user_id: str, item_key: str) -> GeneralResponse:
        inject(self.headers)
        url = (
            f"{self.endpoint}/services/v1/{self.orchestrator_name}"
            f"/users/{user_id}/context/{item_key}"
        )

        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.delete(url) as response:
                    response.raise_for_status()
                    response_data = await response.json()
            except aiohttp.ClientResponseError as e:
                error_detail = await e.response.text()
                raise Exception(f"ERROR: {json.loads(error_detail)['detail']}") from e
        return GeneralResponse(**response_data)

    async def get_context_items(self, user_id: str) -> dict[str, str | None]:
        inject(self.headers)
        async with aiohttp.ClientSession(headers=self.headers) as session:
            try:
                async with session.get(
                    url=f"{self.endpoint}/services/v1/{self.orchestrator_name}/users/{user_id}/context"
                ) as response:
                    response.raise_for_status()
                    response_data = await response.json()
            except aiohttp.ClientResponseError as e:
                error_detail = await e.response.text()
                raise Exception(f"ERROR: {json.loads(error_detail)['detail']}") from e
        return response_data
