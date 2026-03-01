import { Suspense } from 'react';
import chat from '/chat.svg';
import styles from './appStyles.module.css';
import {
    AnimatedBackground,
    PageBody,
} from '@/components';

function App() {
    return (
        <div className={styles.page}>
            <AnimatedBackground />
            <header className={styles.headerMain}>
                <img
                    className={styles.logo}
                    src={chat}
                    alt='chat'
                    width={50}
                    height={50}
                />
                <div className={styles.headerDiv}>
                    <h1 className={styles.header}>
                        Chat App
                    </h1>
                </div>
            </header>
            <Suspense fallback={<div>Loading...</div>}>
                <PageBody />
            </Suspense>
        </div>
    );
};

export default App;