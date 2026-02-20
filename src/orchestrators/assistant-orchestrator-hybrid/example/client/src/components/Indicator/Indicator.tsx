import { useGlobalState } from '@/hooks';
import { WEB_SOCKET_STATE } from '@/types';
import styles from './style.module.css';

const getStatusStyle = (status: WEB_SOCKET_STATE) => {
    switch (status) {
        case WEB_SOCKET_STATE.OPEN:
            return styles.connected;
        case WEB_SOCKET_STATE.CLOSED:
            return styles.disconnected;
        default:
            return styles.notReady;
    }
};

export const Indicator = () => {
    const { webSocketStatus, togglePerf } = useGlobalState();
    const connectedClass = getStatusStyle(webSocketStatus);
    if (webSocketStatus === WEB_SOCKET_STATE.OPEN) {
        return (
            <button className={connectedClass} onClick={togglePerf}/>
        )
    }
    return (
        <div className={connectedClass}></div>
    )
}