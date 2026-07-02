import { RefreshCw } from 'lucide-react';
import { useState } from 'react';

import type { DashboardModel } from '../../api/types';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { MetricCard } from '../../components/MetricCard';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { weeklyColumns } from '../shared/tables';

export function UsageDrainPage({ model }: { model: DashboardModel }) {
  const [refreshStatus, setRefreshStatus] = useState('Snapshot loaded');

  function refreshDiagnostics() {
    setRefreshStatus(`Diagnostics refreshed ${new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date())}`);
  }

  return (
    <div className="lab-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Usage Drain Lab</h1>
          <p>Weekly credits, visible usage remaining, model controls, and fast-mode proxy signals.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label="Local Only" tone="green" />
          <StatusBadge label={refreshStatus} tone="blue" />
          <button className="primary-button" type="button" onClick={refreshDiagnostics}>
            <RefreshCw size={16} /> Refresh Diagnostics
          </button>
        </div>
      </div>
      <div className="metric-grid span-all">
        {model.cards.slice(0, 5).map(card => (
          <MetricCard key={card.label} card={card} />
        ))}
      </div>
      <div className="stacked-panels">
        <Panel title="Projected Weekly Credits Over Time" subtitle="Plan trend with 95% confidence intervals">
          <LineChart series={model.weeklyCreditSeries} yLabel="Credits" />
        </Panel>
        <Panel title="Usage Remaining Over Time" subtitle="Percent remaining against allowance guide">
          <LineChart series={model.usageRemainingSeries} yLabel="Percent remaining" valueFormatter={value => `${value}%`} />
        </Panel>
        <Panel title="Token-Derived Credits vs Visible Usage Drain" subtitle="Correlation view for Pro windows">
          <LineChart series={model.actualVsPredictedSeries} yLabel="Credits" />
        </Panel>
        <Panel title="Weekly Windows" subtitle="Plan-specific windows and caveats">
          <DataTable columns={weeklyColumns} data={model.weeklyWindows} compact />
        </Panel>
      </div>
      <aside className="side-panel">
        <Panel title="Model / Effort Controls">
          <div className="form-grid">
            <label>
              Plan
              <select defaultValue="Pro">
                <option>Pro</option>
                <option>Prolite</option>
                <option>Unknown</option>
              </select>
            </label>
            <label>
              Effort Filter
              <select defaultValue="All">
                <option>All</option>
                <option>High</option>
                <option>Medium</option>
                <option>Low</option>
              </select>
            </label>
            <label className="toggle-row">
              <input type="checkbox" defaultChecked /> Include subagents
            </label>
            <label className="toggle-row">
              <input type="checkbox" defaultChecked /> Include archived
            </label>
          </div>
        </Panel>
        <Panel title="Fast Mode Analysis">
          <div className="form-grid">
            <label className="toggle-row">
              <input type="checkbox" defaultChecked /> Enable proxy
            </label>
            <label>
              Min sample size
              <input type="number" defaultValue={20} />
            </label>
            <label>
              Confidence threshold
              <select defaultValue="0.70">
                <option value="0.70">0.70 High</option>
                <option value="0.55">0.55 Medium</option>
              </select>
            </label>
          </div>
        </Panel>
        <Panel title="Caveats & Method">
          <ul className="compact-list">
            <li>Aggregate-only. Private content excluded.</li>
            <li>Credits estimated from token billing rates and local rate cards.</li>
            <li>Visible usage from the 5h counter is noisy.</li>
            <li>Projection bands are local observations, not universal limits.</li>
          </ul>
        </Panel>
      </aside>
    </div>
  );
}
