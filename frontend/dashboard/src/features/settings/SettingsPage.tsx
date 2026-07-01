import { Database, LockKeyhole, RefreshCw } from 'lucide-react';

import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';

export function SettingsPage() {
  return (
    <div className="page-grid">
      <div className="page-title-row">
        <div>
          <h1>Settings</h1>
          <p>Local dashboard configuration and privacy state.</p>
        </div>
        <StatusBadge label="Local data only" tone="green" />
      </div>
      <div className="dashboard-grid two">
        <Panel title="Data Sources">
          <div className="setting-list">
            <span>
              <Database size={18} /> SQLite index <strong>codex_usage.db</strong>
            </span>
            <span>
              <RefreshCw size={18} /> Refresh mode <strong>Manual</strong>
            </span>
            <span>
              <LockKeyhole size={18} /> Raw context <strong>Explicit only</strong>
            </span>
          </div>
        </Panel>
        <Panel title="Privacy Boundary">
          <ul className="compact-list">
            <li>No prompts or assistant text are included in report payloads.</li>
            <li>Tool output and patch text stay out of static snapshots.</li>
            <li>Raw context actions remain gated and on demand.</li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}
