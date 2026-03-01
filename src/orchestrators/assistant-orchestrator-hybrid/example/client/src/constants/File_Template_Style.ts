export const File_Template_Style = `
    <style>
        :root {
            --background: rgb(235, 235, 235);
            --text-color: rgb(30, 30, 30);
            --link: rgb(30, 30, 235);
        }
        @media (prefers-color-scheme: dark) {
        :root {
                --background: rgb(40, 40, 40);
                --text-color: rgb(210, 210, 210);
                --link: rgb(75, 75, 210);
            }
        }
        ::-webkit-scrollbar {
            width: 18px;
            justify-content: center;
        }
        ::-webkit-scrollbar-thumb {
            background-color: var(--scroll);
            border-radius: 50px;
            border-top: 0.2px outset rgba(0, 0, 0, 0.25);
            border-left: 0.2px outset rgba(0, 0, 0, 0.25);
            border-right: 2px outset rgba(0, 0, 0, 0.35);
            border-bottom: 2px outset rgba(0, 0, 0, 0.35);
            outline: 0.2px solid rgba(0, 0, 0, 0.15);
        }
        html,
        body {
            max-width: 100svw;
            max-height: 100vh;
        }
        body {
            color: var(--text-color);
            background: var(--background);
            font-family: Arial, Helvetica, sans-serif;
        }
        * {
            box-sizing: border-box;
            padding: 0;
            margin: 0;
            font-family: 'Lucida Sans', 'Lucida Sans Regular', 'Lucida Grande', 'Lucida Sans Unicode', 'Geneva', Verdana, sans-serif;
        }
        div {
            display: flex;
            flex: 1;
            margin: 10px;
            margin-top: 24px;
            margin-bottom: 24px;
            flex-direction: column;
            border-radius: 14px;
            backdrop-filter: blur(2px);
            border: 0.2px outset rgba(0, 0, 0, 0.15);
            border-bottom: 4px outset rgba(0, 0, 0, 0.5);
            border-right: 4px outset rgba(0, 0, 0, 0.5);
            box-shadow: 3px 3px 6px rgba(0, 0, 0, 0.5);
        }
        b {
            padding: 6px;
            padding-left: 10px;
            font-size: 1.3rem;
            font-weight: bold;
            border-bottom: 2px inset rgba(0, 0, 0, 0.5);
            box-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
        }
        p {
            padding: 8px;
            padding-left: 24px;
            padding-top: 14px;
            padding-bottom: 14px;
            font-size: 1.1rem;
        }
        i {
            display: none;
        }
        a {
            font-style: oblique;
            color: var(--link);
            text-decoration: underline;
        }
    </style>
`;