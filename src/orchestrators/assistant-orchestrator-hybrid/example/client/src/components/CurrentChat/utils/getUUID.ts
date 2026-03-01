import { DEMO_AGENT_ORCHESTRATOR, TICKETS } from '@/constants';

const ticketOrRandom = async (user_id: string) => {
    let uuid = null;
    console.log('Fetching ticket for login');
    if (TICKETS) {
        try {
            const response = await fetch(TICKETS, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    'user_id': user_id,
                }),
            });
            const data = await response.json();
            uuid = data.ticket;
        } catch (e) {
            console.warn(`Failed to fetch ticket: ${e}`);
            console.warn(`Generating random UUID`);
        };
    };
    // If the ticket fetch fails, generate a random UUID
    if (!uuid) {
        uuid = crypto.randomUUID();
    }
    return uuid;
}

export const getUrlAndUUID = async (user_id: string, resume: boolean) => {
    // user_id will always contain a string value or 'default' defined in the global state
    console.log('Using user_id: ' + user_id);

    const uuid = await ticketOrRandom(user_id);
    console.log(`Ticket - ${uuid}`);

    const url = `${DEMO_AGENT_ORCHESTRATOR}${uuid}` + (resume ? '?resume=true' : '');
    return { url, uuid };
};
