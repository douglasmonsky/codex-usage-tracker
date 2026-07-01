import { Download, RefreshCw } from 'lucide-react';

import type { DashboardModel } from '../../api/types';
import { DonutChart } from '../../charts/DonutChart';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { MetricCard } from '../../components/MetricCard';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { callColumns } from '../shared/tables';

type OverviewPageProps = {
  model: DashboardModel;
  onRefresh: () => void;
  refreshState: string;
};

export function OverviewPage({ model, onRefresh, refreshState }: OverviewPageProps) {
  return (
    <div className="page-grid">
      <div className="page-title-row">
        <div>
          <h1>Overview</h1>
          <p>High-level telemetry and usage summary across local aggregate history.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button">
            <Download size={16} /> Export
          </button>
          <button className="primary-button" type="button" onClick={onRefresh}>
            <RefreshCw size={16} /> Refresh Data
          </button>
        </div>
      </div>
      <div className="metric-grid">
        {model.cards.map(card => (
          <MetricCard key={card.label} card={card} />
        ))}
      </div>
      <div className="dashboard-grid three">
        <Panel title="Tokens Over Time" subtitle="Input, output, and cached tokens">
          <LineChart series={model.tokenSeries} yLabel="Tokens" />
        </Panel>
        <Panel title="Cost Over Time" subtitle="Daily estimated cost">
          <LineChart series={model.costSeries} yLabel="USD" valueFormatter={value => `$${value}`} />
        </Panel>
        <Panel title="Cache Composition" subtitle="Current visible calls">
          <DonutChart centerLabel="24.83M" data={model.cacheSegments} />
        </Panel>
      </div>
      <Panel title="Recent Calls" subtitle={refreshState} action={<StatusBadge label="Local data only" tone="green" />}>
        <DataTable columns={callColumns} data={model.calls.slice(0, 6)} compact />
      </Panel>
    </div>
  );
}
