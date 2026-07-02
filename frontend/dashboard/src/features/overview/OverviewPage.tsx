import { Download, RefreshCw } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { DashboardModel } from '../../api/types';
import { DonutChart } from '../../charts/DonutChart';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { MetricCard } from '../../components/MetricCard';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { rowMatchesQuery } from '../shared/filtering';
import { callColumns, callCsvColumns } from '../shared/tables';

type OverviewPageProps = {
  model: DashboardModel;
  onRefresh: () => void;
  refreshState: string;
  globalQuery: string;
};

export function OverviewPage({ model, onRefresh, refreshState, globalQuery }: OverviewPageProps) {
  const [exportStatus, setExportStatus] = useState('');
  const visibleCalls = useMemo(
    () => model.calls.filter(call => rowMatchesQuery([call.thread, call.model, call.effort, call.signal, call.recommendation], globalQuery)),
    [globalQuery, model.calls],
  );
  const recentCalls = visibleCalls.slice(0, 6);

  function exportRecentCalls() {
    downloadCsv(`codex-overview-calls-${csvDateStamp()}.csv`, rowsToCsv(recentCalls, callCsvColumns));
    setExportStatus(`Exported ${recentCalls.length} visible calls`);
  }

  return (
    <div className="page-grid">
      <div className="page-title-row">
        <div>
          <h1>Overview</h1>
          <p>High-level telemetry usage summary across local aggregate history.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button" onClick={exportRecentCalls} disabled={!recentCalls.length}>
            <Download size={16} />
            Export
          </button>
          <button className="primary-button" type="button" onClick={onRefresh}>
            <RefreshCw size={16} />
            Refresh Data
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
      <Panel
        title="Recent Calls"
        subtitle={exportStatus || refreshState}
        action={<StatusBadge label={globalQuery ? `${visibleCalls.length} matches` : 'Local data only'} tone="green" />}
      >
        <DataTable columns={callColumns} data={recentCalls} compact ariaLabel="Recent calls" />
      </Panel>
    </div>
  );
}
