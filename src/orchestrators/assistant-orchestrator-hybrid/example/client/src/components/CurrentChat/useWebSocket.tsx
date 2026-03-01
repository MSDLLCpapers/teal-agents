import React from 'react';
import { setWebSocketStatus, useGlobalState } from '@/hooks';
import { onMessage, getUrlAndUUID } from './utils';
import { WEB_SOCKET_STATE } from '@/types';
import { INTRO_MSG } from '@/constants';

const useWebSocket = () => {
    const ws = React.useRef<WebSocket | undefined>(undefined);
    const {
        user_id,
        resume,
        handleAssistantResponse,
    } = useGlobalState();

    React.useEffect(() => {
        const initializeWebSocket = async () => {
            if (ws.current) {
                console.warn('ws already initialized, closing and reopening another instance');
                ws.current.close();
            }
            const { url, uuid } = await getUrlAndUUID(user_id, resume);
            ws.current = new WebSocket(url);
            const webSocket = ws.current;

            webSocket.onopen = () => {
                setWebSocketStatus(WEB_SOCKET_STATE.OPEN);
                console.log('ws opened with UUID:', uuid);
            };

            webSocket.onclose = () => {
                setWebSocketStatus(WEB_SOCKET_STATE.CLOSED);
                console.log('ws closed');
            };

            webSocket.onmessage = onMessage.bind(handleAssistantResponse);
        };

        initializeWebSocket();
        handleAssistantResponse(INTRO_MSG);

        return () => {
            if (ws.current) {
                console.log('ws closing');
                ws.current.close();
                ws.current = undefined;
                setWebSocketStatus(WEB_SOCKET_STATE.NOT_READY);
            };
        };
    }, []);

    return ws;
};

export default useWebSocket;
