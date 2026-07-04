import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { App } from './App';
import './styles/tokens.css';
import './styles/base.css';
import './styles/shell.css';
import './styles/controls.css';
import './styles/components.css';
import './styles/charts.css';
import './styles/tables.css';
import './styles/filters.css';
import './styles/investigation.css';
import './styles/context-evidence.css';
import './styles/detail-context.css';
import './styles/dashboard.css';
import './styles/workspaces.css';
import './styles/diagnostics.css';

const root = document.getElementById('root');

if (!root) {
  throw new Error('Dashboard root element was not found.');
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
