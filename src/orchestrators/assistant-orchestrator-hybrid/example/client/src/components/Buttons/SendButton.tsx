import style from './styles.module.css';
import { useGlobalState, useDisableAnimation } from '@/hooks';

export const SendButton = () => {
  const { isUserInputPresent, onSend } = useGlobalState();
  const styles = useDisableAnimation(isUserInputPresent);

  return (
    <button
      style={styles}
      disabled={!isUserInputPresent}
      className={style.btn}
      onClick={onSend}
    >
      Send
    </button>
  )
};
