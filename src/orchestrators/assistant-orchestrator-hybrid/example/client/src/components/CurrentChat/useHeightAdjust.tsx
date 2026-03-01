import React from 'react';
import { useGlobalState } from '@/hooks';
import { CHAT_BOX } from '@/constants';

const useHeightAdjust = () => {
    const elementArea = React.useRef<HTMLDivElement>(null);
    const { userInputHeight, containerHeight } = useGlobalState();

    function adjustHeight() {
        const parentContHeight = containerHeight || window.innerHeight;
        const currentElementArea = elementArea.current;
        if (currentElementArea && userInputHeight) {
            currentElementArea.style.height = `${userInputHeight}px`;
            const min = Math.max(
                parentContHeight * CHAT_BOX.MIN_HEIGHT,
                CHAT_BOX.LOWEST_MIN_HEIGHT,
            );
            currentElementArea.style.minHeight = `${min}px`; // set min height of chat box that it can be
        };
    };

    React.useEffect(adjustHeight, [userInputHeight]);

    return elementArea;
};

export default useHeightAdjust;
