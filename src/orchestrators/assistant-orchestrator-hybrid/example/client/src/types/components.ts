

export type NewContentType = {
    agent_name?: string;
    [key: string]: string | number | boolean | undefined;
};

export enum WEB_SOCKET_STATE {
    OPEN = 'OPEN',
    CLOSED = 'CLOSED',
    NOT_READY = 'NOT_READY_YET',
};
