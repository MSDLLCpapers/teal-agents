from typing import List, Dict, Annotated
from fastapi import (
    WebSocket,
    WebSocketException,
    status,
)
from ska_utils import AppConfig, strtobool, initialize_telemetry, get_telemetry
from configs import TA_AUTH_ENABLED
from services import new_client, ServicesClient

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(
        self, service_name: str, websocket: WebSocket, ticket: str
    ) -> str:
        cfg = AppConfig()
        if strtobool(str(cfg.get(TA_AUTH_ENABLED.env_name))):
            services_client: ServicesClient = new_client(service_name)
            result = services_client.verify_ticket(ticket, websocket.client.host)
            if not result.is_valid:
                raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
            user_id = result.user_id
        else:
            user_id = "default"
        await websocket.accept()
        self.active_connections.append(websocket)
        return user_id

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
