import { useLayoutEffect, useRef } from 'react';
import { setContainerHeight } from "@/hooks";

export const useHandleResize = () => {
    const divRef = useRef<HTMLDivElement>(null);

    const setHeight = () => {
        if (divRef.current) {
            // Get the root font size in pixels
            setContainerHeight(divRef.current.offsetHeight);
        }
    }

    useLayoutEffect(() => {
        setHeight();
        window.addEventListener('resize', setHeight);
        return () => window.removeEventListener('resize', setHeight);
    }, []);

    return divRef;
};
