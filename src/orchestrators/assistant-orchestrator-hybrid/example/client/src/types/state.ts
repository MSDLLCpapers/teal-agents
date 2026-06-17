import { WEB_SOCKET_STATE } from './components';

export enum ChatRole {
    User = 'User',
    Assistant = 'Assistant',
};

export type ChatItem = {
    role: ChatRole;
    content: string;
    time?: string;
};

export type PerformanceLogging = {
    startTime: number | undefined;
    perfTime: string | undefined;
    showPerfLogging: boolean;
};

export interface GlobalState {
    chatHistory: ChatItem[];
    userInput: string;
    performance: PerformanceLogging;
    urlParams: {
        user_id: string | undefined;
        resume: boolean;
    };
    userInputHeight: number | undefined;
    containerHeight: number | undefined;
    webSocketStatus: WEB_SOCKET_STATE;
};
