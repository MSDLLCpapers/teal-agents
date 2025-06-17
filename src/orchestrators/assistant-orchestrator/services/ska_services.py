import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pynamodb.exceptions import DeleteError, DoesNotExist
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

logger = logging.getLogger(__name__)

AppConfig.add_configs(CONFIGS)
app_config = AppConfig()

initialize_telemetry("Agent-Services", app_config)

# Instance of FastAPI app
app = FastAPI(
    openapi_url="/services/v1/openapi.json",
    docs_url="/services/v1/docs",
    redoc_url="/services/v1/redoc",
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, ex: HTTPException):
    logger.warning(
        f"HTTP {ex.status_code} error during {request.method} {request.url.path}",
        extra={"headers": dict(request.headers), "detail": ex.detail},
    )
    return JSONResponse(
        status_code=ex.status_code,
        content={
            "detail": ex.detail,
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, ex: Exception):
    logger.exception(f"Unexpected error: {str(ex)}")

    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error has occured, check logs for further information",
            "path": request.url.path,
        },
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
        try:
            return CreateTicketResponse(
                ticket=ticket_manager.create_ticket(
                    orchestrator_name, auth_response.user_id, ip_address
                )
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"{type(e).__name__} - {e.msg}",
            ) from e
    else:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication Failed")


@app.post("/services/v1/{orchestrator_name}/tickets/verify", tags=["Tickets"])
async def verify_ticket(
    orchestrator_name: str, payload: VerifyTicketRequest, request: Request
) -> VerifyTicketResponse:
    try:
        return ticket_manager.verify_ticket(orchestrator_name, payload.ticket, payload.ip_address)
    except DoesNotExist as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{type(e).__name__} - {e.msg}"
        ) from e


@app.post(
    "/services/v1/{orchestrator_name}/conversation-history",
    tags=["Conversation History"],
)
async def new_conversation(
    orchestrator_name: str, payload: NewConversationRequest, request: Request
) -> ConversationResponse:
    try:
        return await conversation_manager.new_conversation(
            orchestrator_name, payload.user_id, payload.is_resumed
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} - {e.msg}",
        ) from e


@app.get(
    "/services/v1/{orchestrator_name}/conversation-history/{conversation_id}",
    tags=["Conversation History"],
)
async def get_conversation_message(
    orchestrator_name: str, payload: GetConversationRequest, request: Request
) -> ConversationResponse:
    try:
        return await conversation_manager.get_conversation(
            orchestrator_name, payload.user_id, payload.session_id
        )
    except DoesNotExist as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{type(e).__name__} - {e.msg}"
        ) from e


@app.post(
    "/services/v1/{orchestrator_name}/conversation-history/{conversation_id}/messages",
    tags=["Conversation History"],
)
async def add_conversation_message(
    orchestrator_name: str,
    conversation_id: str,
    request: AddConversationMessageRequest,
) -> GeneralResponse:
    try:
        return await conversation_manager.add_conversation_message(
            orchestrator_name=orchestrator_name,
            conversation_id=conversation_id,
            message_type=request.message_type,
            agent_name=request.agent_name,
            message=request.message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} - {e.msg}",
        ) from e


@app.post("/services/v1/{orchestrator_name}/users/{user_id}/context", tags=["Users"])
async def create_context_item(
    orchestrator_name: str, user_id: str, request: AddContextItemRequest
) -> GeneralResponse:
    try:
        await context_manager.add_context(
            orchestrator_name, user_id, request.item_key, request.item_value
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} - {e.msg}",
        ) from e
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
    try:
        await context_manager.update_context(
            orchestrator_name, user_id, item_key, request.item_value
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} - {e.msg}",
        ) from e
    return GeneralResponse(status=200, message="Context item updated successfully")


@app.delete(
    "/services/v1/{orchestrator_name}/users/{user_id}/context/{item_key}",
    tags=["Users"],
)
async def delete_context_item(
    orchestrator_name: str, user_id: str, item_key: str
) -> GeneralResponse:
    try:
        await context_manager.delete_context(orchestrator_name, user_id, item_key)
    except DoesNotExist as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"{type(e).__name__} - {e.msg}"
        ) from e
    except DeleteError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} - {e.msg}",
        ) from e
    return GeneralResponse(status=200, message="Context item deleted successfully")


@app.get("/services/v1/{orchestrator_name}/users/{user_id}/context", tags=["Users"])
async def get_context_items(orchestrator_name: str, user_id: str) -> dict[str, str]:
    try:
        return await context_manager.get_context(orchestrator_name, user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{type(e).__name__} - {e.msg}",
        ) from e


@app.get(
    "/services/v1/{orchestrator_name}/healthcheck",
    tags=["Health"],
    description="Check the health status of ska services.",
)
async def healthcheck():
    return {"status": "healthy"}
