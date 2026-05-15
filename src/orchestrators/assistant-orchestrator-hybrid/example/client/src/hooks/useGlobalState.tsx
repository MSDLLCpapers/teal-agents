import { hookstate, useHookstate } from '@hookstate/core';
import { useCallback, useMemo } from 'react';
import { ChatItem, ChatRole, GlobalState, WEB_SOCKET_STATE } from '@/types';
import { INTRO_MSG } from '@/constants';

const initialState: GlobalState = {
    chatHistory: [],
    userInput: '',
    performance: {
        startTime: undefined,
        perfTime: undefined,
        showPerfLogging: false,
    },
    urlParams: {
        user_id: undefined,
        resume: false,
    },
    userInputHeight: undefined,
    containerHeight: undefined,
    webSocketStatus: WEB_SOCKET_STATE.NOT_READY,
};

const globalState = hookstate(initialState);

export const useSetValuesFromUrlParams = () => {
    const searchParams = new URLSearchParams(window.location.search);
    const user_id = searchParams.get('user_id') || 'default';
    const resume = searchParams.get('resume') ? true : false;
    globalState.urlParams.user_id.set(user_id);
    globalState.urlParams.resume.set(resume);
};

export const setUserInputHeight = (current: number) => {
    globalState.userInputHeight.set(current);
};

export const setContainerHeight = (current: number) => {
    globalState.containerHeight.set(current);
};

export const logPerformance = () => {
    if (globalState.performance.startTime.value === undefined) {
        return;
    };
    const perf = performance.now() - globalState.performance.startTime.value;
    const perfTime = perf > 1000 ? parseFloat((perf / 1000).toFixed(2)) + 's' : parseFloat(perf.toFixed(2)) + 'ms';
    globalState.performance.perfTime.set(perfTime);
    console.log(`Time from user input to response: ${perf}ms`);
    globalState.performance.startTime.set(undefined);
};

export const setWebSocketStatus = (state: WEB_SOCKET_STATE) => {
    globalState.webSocketStatus.set(state);
};

export const useGlobalState = () => {
    const state = useHookstate(globalState);

    const setUserInput = (message?: string) => {
        state.userInput.set(message || '');
    };
    const lastChatItem = useMemo(() => {
        return state.chatHistory.length > 0 ? state.chatHistory[state.chatHistory.length - 1].value : undefined;
    }, [state.chatHistory.value]);

    const isUserInputPresent = useMemo(() => {
        return Boolean(state.userInput.value.trim());
    }, [state.userInput.value.trim()]);

    const isChatHistoryPresent = useMemo(() => {
        return lastChatItem && (
            lastChatItem.role === ChatRole.User ||
            lastChatItem.content !== INTRO_MSG
        );
    }, [lastChatItem]);

    const initializePerfTime = useCallback(() => {
        const perf = performance.now();
        state.performance.startTime.set(perf);
        state.performance.perfTime.set(undefined);
    }, [
        state.performance.startTime.value,
        state.performance.perfTime.value,
    ]);
    
    const onSend = useCallback(() => {
        if (!isUserInputPresent) {
            return;
        };
        try {
            initializePerfTime();
            const content = state.userInput.value;
            if (!content) {
                return;
            } else {
                state.chatHistory.merge([{
                    role: ChatRole.User,
                    content: content,
                }]);
            };
        } catch (e) {
            console.error('Error sending userInput:', e);
        } finally {
            setUserInput();
        };
    }, [
        isUserInputPresent,
        state.userInput.value,
        state.chatHistory.value,
        state.performance.startTime.value,
        state.performance.perfTime.value,
        setUserInput,
        initializePerfTime,
    ]);

    const handleAssistantResponse = useCallback((content: string) => {
        if (!content) {
            return;
        };
        const currentChatHistory = state.chatHistory.value;
        const chatHistLength = currentChatHistory.length;
        const perfTime = state.performance.perfTime.value;
        const lastChat = currentChatHistory[chatHistLength - 1];

        // This is to merge incoming message stream
        if (lastChat?.role === ChatRole.Assistant && lastChat?.content !== INTRO_MSG) {
            state.chatHistory[currentChatHistory.length - 1].content.merge(content);
        } else {
            // This is for a new stream
            const newMsg: ChatItem = {
                role: ChatRole.Assistant,
                content: content,
            };
            if (perfTime) {
                newMsg.time = perfTime;
            };
            state.chatHistory.merge([newMsg]);
        }
    }, [
        state.chatHistory.value,
        state.performance.perfTime.value,
    ]);

    const togglePerf = () => {
        const perfLogging = state.performance.showPerfLogging;
        const val = perfLogging.value;
        perfLogging.set(!val);
    };

    return {
        chatHistory: state.chatHistory.value,
        lastChatItem: lastChatItem,
        user_id: state.urlParams.user_id.value || '',
        resume: state.urlParams.resume.value,
        userInput: state.userInput.value,
        startTime: state.performance.startTime.value,
        webSocketStatus: state.webSocketStatus.value,
        userInputHeight: state.userInputHeight.value,
        containerHeight: state.containerHeight.value,
        isUserInputPresent,
        isChatHistoryPresent,
        showPerformance: state.performance.showPerfLogging.value,
        setUserInput,
        onSend,
        handleAssistantResponse,
        togglePerf,
    };
};
