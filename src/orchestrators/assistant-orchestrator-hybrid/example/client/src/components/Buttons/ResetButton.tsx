import { useDisableAnimation, useGlobalState } from '@/hooks';
import style from './styles.module.css';

export const ResetButton = () => {
    const { isChatHistoryPresent, isUserInputPresent, startTime } = useGlobalState();
    
    const notDisabled = Boolean(isUserInputPresent || isChatHistoryPresent || startTime);
    const styles = useDisableAnimation(notDisabled);

    const refresh = () => {
        window.location.reload();
    };

    return (
        <button
            style={styles}
            disabled={!notDisabled}
            className={style.btn}
            onClick={refresh}
        >
            Reset
        </button>
    )
};
