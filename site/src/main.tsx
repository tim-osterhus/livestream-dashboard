import { React, ReactDOM } from './react-global.js';
import { App } from './app.js';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Missing #root container');
}

const root = ReactDOM.createRoot(rootElement);
root.render(<App />);
