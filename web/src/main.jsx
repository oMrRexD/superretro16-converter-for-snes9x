import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/press-start-2p/latin.css';
import '@fontsource/vt323/latin.css';
import '@fontsource/jetbrains-mono/latin.css';
import '@fontsource/space-grotesk/latin.css';
import App from './App.jsx';
import { installSiteIcons } from './siteMeta.js';
import './styles.css';

installSiteIcons();

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
