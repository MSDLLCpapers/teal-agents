import React from 'react';
import styles from './styles.module.css';
import { useGlobalState } from '@/hooks';
import { ButtonGroup } from '@/components/Buttons';
import useHeightAdjust from './useHeightAdjust';

export const UserInputBox = () => {
    const { userInput, setUserInput, onSend } = useGlobalState();
    const textArea = useHeightAdjust();

    function handleChange(ev: React.ChangeEvent<HTMLTextAreaElement>) {
        setUserInput(ev.target.value);
    };

    function handleKeyDown(ev: React.KeyboardEvent<HTMLTextAreaElement>) {
        if (ev.key === 'Enter' && !ev.shiftKey) {
            ev.preventDefault();
            onSend();
        };
    };

    return (
        <div className={styles.main} >
            <div className={styles.userInBox} id='userInBox'>
                <textarea
                    placeholder='Enter your message here...'
                    value={userInput}
                    ref={textArea}
                    className={styles.content}
                    onChange={handleChange}
                    onKeyDown={handleKeyDown}
                />
            </div>
            <ButtonGroup />
        </div>
    );
};
