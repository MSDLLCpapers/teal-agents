import { CurrentChat, UserInputBox } from '@/components';
import { useGlobalState, useHandleResize, useSetValuesFromUrlParams } from '@/hooks';
import styles from './styles.module.css';

export const PageBody = () => {
    useSetValuesFromUrlParams();
    const { user_id } = useGlobalState();
    const divRef = useHandleResize();

    return (
        <div className={styles.body} ref={divRef}>
            {
                user_id ?
                    <>
                        <CurrentChat />
                        <UserInputBox />
                    </>
                    :
                    <></>
            }
        </div>
    );
};
