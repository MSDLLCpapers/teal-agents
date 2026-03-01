import React from 'react';
import { setUserInputHeight, useGlobalState } from '@/hooks';
import { USER_INPUT } from '@/constants';

const useHeightAdjust = () => {
    const elementArea = React.useRef<HTMLTextAreaElement>(null);
    const { userInput, containerHeight } = useGlobalState();

    function adjustHeight() {
        const parentContHeight = containerHeight || window.innerHeight;
        const currentElem = elementArea?.current;
        if (currentElem) {
            currentElem.style.height = 'auto'; // Reset height to get the scrollHeight
            const max = parentContHeight * USER_INPUT.MAX_HEIGHT;
            const min = Math.max(
                parentContHeight * USER_INPUT.MIN_HEIGHT,
                USER_INPUT.LOWEST_MIN_HEIGHT,
            );
            currentElem.style.minHeight = `${min}px`; // Set min height text area can be resized to
            currentElem.style.maxHeight = `${max}px`; // Set max height text area can be resized to
            currentElem.style.height = `${currentElem.scrollHeight}px`; // Set the new height

            const currentChatHeight = parentContHeight - currentElem.offsetHeight - USER_INPUT.ADJUSTED_OFFSET;
            setUserInputHeight(currentChatHeight);
        }
    }

    React.useEffect(adjustHeight, [userInput, containerHeight]);

    return elementArea;
};

export default useHeightAdjust;
