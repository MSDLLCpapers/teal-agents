import { ResetButton } from "./ResetButton"
import { SendButton } from "./SendButton"
import style from './styles.module.css';

export const ButtonGroup = () => {
    return (
        <div className={style.btnGroup}>
            <ResetButton />
            <SendButton />
        </div>
    );
};
