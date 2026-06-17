import style from './styles.module.css';
import { File_Template_Style } from '@/constants';
import { useDisableAnimation, useGlobalState } from '@/hooks';

export const DownloadButton = ({ chatBox }: { chatBox: HTMLDivElement | null }) => {
    const { isChatHistoryPresent } = useGlobalState();
    const styles = useDisableAnimation(isChatHistoryPresent);

    const downloadPress = () => {
        if (chatBox) {
            const element = document.createElement('a');
            const file = new Blob([File_Template_Style + chatBox.innerHTML], { type: 'text/html' });
            element.href = URL.createObjectURL(file);
            element.download = 'chat.html';
            element.click();
        };
    };

    return (
        <button
            style={styles}
            type='button'
            className={style.downloadBtn}
            onClick={downloadPress}
        >
            Download
        </button>
    );
};
