import { WEB_SOCKET_STATE } from '@/types';

export const getWebSocketState = (ws: WebSocket | undefined): WEB_SOCKET_STATE => {
    if (!ws) {
        return WEB_SOCKET_STATE.NOT_READY;
    } else {
        switch (ws.readyState) {
            case WebSocket.CONNECTING:
                return WEB_SOCKET_STATE.NOT_READY;
            case WebSocket.OPEN:
                return WEB_SOCKET_STATE.OPEN;
            default:
                return WEB_SOCKET_STATE.CLOSED;
        };
    };
};
