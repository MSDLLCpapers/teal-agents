import { useState, useEffect } from 'react';
import styles from './styles.module.css';

function getRandomColor() {
    const letters = '0123456789ABCDEF';
    let color = '#';
    for (let i = 0; i < 6; i++) {
        color += letters[Math.floor(Math.random() * 16)];
    }
    return color;
};

const AnimGroup = () => {
    const [colors, setColors] = useState({
        color1: getRandomColor(),
        color2: getRandomColor(),
        color3: getRandomColor(),
    });

    useEffect(() => {
        const interval = setInterval(() => {
            setColors({
                color1: getRandomColor(),
                color2: getRandomColor(),
                color3: getRandomColor()
            });
        }, 8000); // Change colors every 7 seconds

        return () => clearInterval(interval);
    }, []);

    return (
        <>
            <div className={styles.box} style={{
                borderTopColor: colors.color1,
                filter: `drop-shadow(0 0 5px ${colors.color1}) drop-shadow(0 0 15px ${colors.color1}) drop-shadow(0 0 25px ${colors.color1})`,
            }} suppressHydrationWarning />
            <div className={styles.box} style={{
                borderLeftColor: colors.color2,
                filter: `drop-shadow(0 0 5px ${colors.color2}) drop-shadow(0 0 15px ${colors.color2}) drop-shadow(0 0 25px ${colors.color2})`,
            }} suppressHydrationWarning />
            <div className={styles.box} style={{
                borderLeftColor: colors.color3,
                filter: `drop-shadow(0 0 5px ${colors.color3}) drop-shadow(0 0 15px ${colors.color3}) drop-shadow(0 0 25px ${colors.color3})`,
            }} suppressHydrationWarning />
        </>
    );
};

export const AnimatedBackground = () => (
    <div className={styles.main}>
        <div className={styles.group1}>
            <AnimGroup />
        </div>
        <div className={styles.group2}>
            <AnimGroup />
        </div>
    </div>
);
