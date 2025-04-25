from fastapi import FastAPI, HTTPException, Request, status
from pynamodb.exceptions import DoesNotExist
from ska_utils import AppConfig, get_telemetry, initialize_telemetry, strtobool

from auth import Authenticator, CustomAuthHelper
from configs import CONFIGS, TA_KONG_ENABLED
from data import (
    ContextManager,
    ConversationManager,
    TicketManager,
    get_chat_history_manager,
    get_context_manager,
    get_ticket_manager,
)
from middleware import TelemetryMiddleware
from model import (
    AddContextItemRequest,
    AddConversationMessageRequest,
    AuthenticationResponse,
    ConversationResponse,
    GeneralResponse,
    GetConversationRequest,
    NewConversationRequest,
    UpdateContextItemRequest,
)
from model.requests import VerifyTicketRequest
from model.responses import CreateTicketResponse, VerifyTicketResponse

AppConfig.add_configs(CONFIGS)
app_config = AppConfig()

initialize_telemetry("Agent-Services", app_config)

# Instance of FastAPI app
app = FastAPI(
    openapi_url="/services/v1/openapi.json",
    docs_url="/services/v1/docs",
    redoc_url="/services/v1/redoc",
)

# noinspection PyTypeChecker
app.add_middleware(TelemetryMiddleware, st=get_telemetry())

conversation_manager: ConversationManager = ConversationManager(get_chat_history_manager())
ticket_manager: TicketManager = get_ticket_manager()
context_manager: ContextManager = get_context_manager()

auth_helper: CustomAuthHelper = CustomAuthHelper(app_config)
authenticator: Authenticator[auth_helper.get_request_type()] = auth_helper.get_authenticator()


@app.post("/services/v1/{orchestrator_name}/authenticate")
async def authenticate_user(
    orchestrator_name: str, payload: auth_helper.get_request_type()
) -> AuthenticationResponse:
    auth_response = authenticator.authenticate(orchestrator_name, payload)
    if auth_response.success:
        return AuthenticationResponse(
            orchestrator_name=auth_response.orch_name, user_id=auth_response.user_id
        )
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication Failed")


@app.post("/services/v1/{orchestrator_name}/tickets", tags=["Tickets"])
async def create_ticket(
    orchestrator_name: str, payload: auth_helper.get_request_type(), request: Request
) -> CreateTicketResponse:
    ip_address: str
    if strtobool(str(app_config.get(TA_KONG_ENABLED.env_name))):
        ip_address = request.headers.get("X-Forwarded-For")
    else:
        ip_address = request.client.host
    auth_response = authenticator.authenticate(orchestrator_name, payload)
    if auth_response.success:
        return CreateTicketResponse(
            ticket=ticket_manager.create_ticket(
                orchestrator_name, auth_response.user_id, ip_address
            )
        )
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication Failed")


@app.post("/services/v1/{orchestrator_name}/tickets/verify", tags=["Tickets"])
async def verify_ticket(
    orchestrator_name: str, payload: VerifyTicketRequest, request: Request
) -> VerifyTicketResponse:
    return ticket_manager.verify_ticket(orchestrator_name, payload.ticket, payload.ip_address)


@app.post(
    "/services/v1/{orchestrator_name}/conversation-history",
    tags=["Conversation History"],
)
async def new_conversation(
    orchestrator_name: str, payload: NewConversationRequest, request: Request
) -> ConversationResponse:
    return conversation_manager.new_conversation(
        orchestrator_name, payload.user_id, payload.is_resumed
    )


@app.get(
    "/services/v1/{orchestrator_name}/conversation-history/{conversation_id}",
    tags=["Conversation History"],
)
async def get_conversation_message(
    orchestrator_name: str, payload: GetConversationRequest, request: Request
) -> ConversationResponse:
    return conversation_manager.get_conversation(
        orchestrator_name, payload.user_id, payload.session_id
    )


@app.post(
    "/services/v1/{orchestrator_name}/conversation-history/{conversation_id}/messages",
    tags=["Conversation History"],
)
async def add_conversation_message(
    orchestrator_name: str,
    conversation_id: str,
    request: AddConversationMessageRequest,
) -> GeneralResponse:
    return conversation_manager.add_conversation_message(
        orchestrator_name=orchestrator_name,
        conversation_id=conversation_id,
        message_type=request.message_type,
        agent_name=request.agent_name,
        message=request.message,
    )


@app.post("/services/v1/{orchestrator_name}/users/{user_id}/context", tags=["Users"])
async def create_context_item(
    orchestrator_name: str, user_id: str, request: AddContextItemRequest
) -> GeneralResponse:
    context_manager.add_context(orchestrator_name, user_id, request.item_key, request.item_value)
    return GeneralResponse(status=200, message="Context item added successfully")


@app.put(
    "/services/v1/{orchestrator_name}/users/{user_id}/context/{item_key}",
    tags=["Users"],
)
async def update_context_item(
    orchestrator_name: str,
    user_id: str,
    item_key: str,
    request: UpdateContextItemRequest,
) -> GeneralResponse:
    context_manager.update_context(orchestrator_name, user_id, item_key, request.item_value)
    return GeneralResponse(status=200, message="Context item updated successfully")


@app.delete(
    "/services/v1/{orchestrator_name}/users/{user_id}/context/{item_key}",
    tags=["Users"],
)
async def delete_context_item(
    orchestrator_name: str, user_id: str, item_key: str
) -> GeneralResponse:
    try:
        context_manager.delete_context(orchestrator_name, user_id, item_key)
    except DoesNotExist:
        raise HTTPException(status_code=404, detail="Context item not found")
    return GeneralResponse(status=200, message="Context item deleted successfully")


@app.get("/services/v1/{orchestrator_name}/users/{user_id}/context", tags=["Users"])
async def get_context_items(orchestrator_name: str, user_id: str) -> dict[str, str]:
    return context_manager.get_context(orchestrator_name, user_id)


@app.get(
    "/services/v1/{orchestrator_name}/healthcheck",
    tags=["Health"],
    description="Check the health status of ska services.",
)
async def healthcheck():
    return {"status": "healthy"}
