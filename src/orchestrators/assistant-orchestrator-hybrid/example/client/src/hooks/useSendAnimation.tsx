import React from 'react';

export const useDisableAnimation = (check: string | boolean | number | null | undefined) => {
    const [opacity, setOpacity] = React.useState(0);
    const [display, setDisplay] = React.useState('none');

    React.useEffect(() => {
        if (check) {
            setOpacity(1);
            setDisplay('block');
            setTimeout(() => {
                setDisplay('block');
            }, 290);
        } else {
            setOpacity(0);
            setTimeout(() => {
                setDisplay('none');
            }, 290);
        }
    }, [check]);

    return { opacity, display };
};
