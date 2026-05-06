import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.jsx';
import { installSiteIcons } from './siteMeta.js';
import './styles.css';

installSiteIcons();

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
