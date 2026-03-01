import { useEffect } from 'react';
import { setWebSocketStatus, useGlobalState } from '@/hooks';
import { Indicator, DownloadButton } from '@/components';
import { ChatRole, WEB_SOCKET_STATE } from '@/types';
import styles from './styles.module.css';
import useWebSocket from './useWebSocket';
import useHeightAdjust from './useHeightAdjust';
import { getWebSocketState } from './utils';

export const CurrentChat = () => {
    console.log(`RENDERED CurrentChat`);
    const ws = useWebSocket();
    const { chatHistory, lastChatItem, showPerformance } = useGlobalState();
    const chatBox = useHeightAdjust();

    useEffect(() => {
        const wsStatus = getWebSocketState(ws.current);
        setWebSocketStatus(wsStatus);
        if (wsStatus !== WEB_SOCKET_STATE.OPEN) {
            return;
        };
        if (lastChatItem?.role === ChatRole.User) {
            ws.current?.send(lastChatItem.content);
        };
    }, [lastChatItem?.role, lastChatItem?.content, ws.current]);

    useEffect(() => {
        if (chatBox.current) {
            chatBox.current.innerHTML = chatHistory.map(({ role, content, time }) => {
                const timeStr = showPerformance && time ? `<i>${time}</i>` : '';
                const linkifiedContent = role === ChatRole.Assistant ? content.replace(
                    /(https?:\/\/[^\s",'\)\}\]]+)/g,
                    '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>',
                ) : content;
                return (`
                    <div>
                        <b>${role}:</b>
                        ${timeStr}
                        <p>${linkifiedContent.replaceAll('\n', '<br/>')}</p>
                    </div>
                `);
            }).join('');
            chatBox.current.scrollTo(0, chatBox.current.scrollHeight);
        };
    }, [chatBox.current, chatHistory]);

    return (
        <div className={styles.currentChat}>
            <div className={styles.titleDiv}>
                <p className={styles.titleText}>Chat</p>
                <Indicator />
            </div>
            <DownloadButton chatBox={chatBox.current} />
            <div ref={chatBox} className={styles.content} />
        </div>
    );
};
