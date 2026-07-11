import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

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

const reactRoot = createRoot(root);

async function mountDashboard() {
  const isVisualContractLab =
    import.meta.env.DEV && new URLSearchParams(window.location.search).get('lab') === 'visual-contract';
  if (isVisualContractLab) {
    const { VisualContractLab } = await import('./design/lab/VisualContractLab');
    reactRoot.render(
      <StrictMode>
        <VisualContractLab />
      </StrictMode>,
    );
    return;
  }

  const [{ RouterProvider }, { dashboardRouter }] = await Promise.all([
    import('@tanstack/react-router'),
    import('./app/dashboardRouter'),
  ]);
  reactRoot.render(
    <StrictMode>
      <RouterProvider router={dashboardRouter} />
    </StrictMode>,
  );
}

void mountDashboard();
