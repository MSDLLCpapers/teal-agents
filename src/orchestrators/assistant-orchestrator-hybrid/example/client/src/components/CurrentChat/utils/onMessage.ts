import { CURRENT_ENV } from '@/constants';
import { logPerformance } from '@/hooks';
import { NewContentType } from '@/types';

export function onMessage(this: (content: string) => void, e: MessageEvent<string>) {
    let newMessage = e?.data;
    try {
        const content: NewContentType = JSON.parse(newMessage);
        if (content.hasOwnProperty('agent_name')) {
            // Log Performance
            logPerformance();
            newMessage = `Handled by: ${content.agent_name}\n\n`;

            // Log Agent Name handling Data
            console.log(newMessage);
        }
    } catch {
        if (CURRENT_ENV === 'development') {
            logPerformance();
        }
    };
    this(newMessage);
};
