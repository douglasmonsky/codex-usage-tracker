import type { ColumnDef } from '@tanstack/react-table';
import { ArrowRight, Download, RefreshCw } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { CallRow, DashboardModel, Finding } from '../../api/types';
import { DonutChart } from '../../charts/DonutChart';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { MetricCard } from '../../components/MetricCard';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { rowMatchesQuery } from '../shared/filtering';
import { formatCompact, formatNumber } from '../shared/format';
import { callActionColumn, callColumns, callCsvColumns, callInvestigatorRowLabel } from '../shared/tables';

type OverviewRuntime = {
  historyScope: string;
  loadLimit: number;
  loadedRowCount: number;
  totalAvailableRows: number;
};

type OverviewPageProps = {
  model: DashboardModel;
  onRefresh: () => void;
  refreshState: string;
  globalQuery: string;
  runtime: OverviewRuntime;
  refreshing: boolean;
  canLoadMoreRows: boolean;
  canLoadAllRows: boolean;
  onLoadMoreRows: () => void;
  onLoadAllRows: () => void;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  onOpenFinding: (rank: number) => void;
};

export function overviewCallsForQuery(calls: CallRow[], globalQuery = ''): CallRow[] {
  return calls.filter(call =>
    rowMatchesQuery([call.thread, call.model, call.effort, call.signal, call.recommendation], globalQuery),
  );
}

export function OverviewPage({
  model,
  onRefresh,
  refreshState,
  globalQuery,
  runtime,
  refreshing,
  canLoadMoreRows,
  canLoadAllRows,
  onLoadMoreRows,
  onLoadAllRows,
  onOpenInvestigator,
  onCopyCallLink,
  onOpenFinding,
}: OverviewPageProps) {
  const [exportStatus, setExportStatus] = useState('');
  const [recentVisibleCount, setRecentVisibleCount] = useState(6);
  const overviewCallColumns = useMemo<Array<ColumnDef<CallRow>>>(
    () => [...callColumns, callActionColumn({ onOpenInvestigator, onCopyCallLink })],
    [onCopyCallLink, onOpenInvestigator],
  );
  const visibleCalls = useMemo(() => overviewCallsForQuery(model.calls, globalQuery), [globalQuery, model.calls]);
  const recentCalls = visibleCalls.slice(0, recentVisibleCount);
  const hiddenLoadedRecentCalls = Math.max(0, visibleCalls.length - recentCalls.length);
  const recentCallsSubtitle = exportStatus
    ? `${exportStatus} - ${recentCallsBasis(recentCalls.length, visibleCalls.length, runtime, Boolean(globalQuery.trim()))}`
    : `${recentCallsBasis(recentCalls.length, visibleCalls.length, runtime, Boolean(globalQuery.trim()))} - ${refreshState}`;

  function exportRecentCalls() {
    downloadCsv(`codex-overview-calls-${csvDateStamp()}.csv`, rowsToCsv(recentCalls, callCsvColumns));
    setExportStatus(`Exported ${recentCalls.length} visible calls`);
  }

  function showMoreRecentCalls() {
    setRecentVisibleCount(count => count + 25);
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
<DonutChart centerLabel={cacheCompositionCenterLabel(model)} data={model.cacheSegments} />
        </Panel>
</div>
<Panel
        title="Needs Attention"
        subtitle="Ranked findings restored from the legacy insights view"
        action={<StatusBadge label={model.findings.length ? `${model.findings.length} findings` : 'No findings'} tone={model.findings.length ? 'orange' : 'green'} />}
      >
        <OverviewFindingsPanel findings={model.findings.slice(0, 3)} onOpenFinding={onOpenFinding} />
      </Panel>
      <Panel
        title="Recent Calls"
        subtitle={recentCallsSubtitle}
        action={
          <div className="panel-action-group">
            <StatusBadge label={globalQuery ? `${visibleCalls.length} matches` : 'Local data only'} tone="green" />
          </div>
        }
      >
        <DataTable
          columns={overviewCallColumns}
          data={recentCalls}
          compact
          getRowId={call => call.id}
          getRowActionLabel={call => callInvestigatorRowLabel(call)}
          onRowActivate={call => onOpenInvestigator(call.id)}
          ariaLabel="Recent calls"
        />
        <div className="table-window-footer recent-calls-footer">
          <span>
            Showing {formatNumber(recentCalls.length)} of {formatNumber(visibleCalls.length)} loaded calls
          </span>
          <div className="panel-action-group">
            <button
              className="table-action-button"
              type="button"
              onClick={showMoreRecentCalls}
              disabled={!hiddenLoadedRecentCalls}
            >
              Show {formatNumber(Math.min(25, hiddenLoadedRecentCalls || 25))} more calls
            </button>
            <button className="table-action-button" type="button" onClick={onLoadMoreRows} disabled={!canLoadMoreRows || refreshing}>
              {refreshing ? 'Loading rows...' : 'Load more rows'}
            </button>
            <button className="table-action-button" type="button" onClick={onLoadAllRows} disabled={!canLoadAllRows || refreshing}>
              Load all rows
            </button>
          </div>
        </div>
      </Panel>
    </div>
  );
}

function OverviewFindingsPanel({
findings,
onOpenFinding,
}: {
findings: Finding[];
onOpenFinding: (rank: number) => void;
}) {
if (!findings.length) {
return <p className="empty-state">No ranked findings in the loaded aggregate snapshot.</p>;
}

return (
<div className="finding-list">
{findings.map(finding => (
<article key={finding.rank} className="finding-card">
<div className="finding-rank">{finding.rank}</div>
<div className="finding-body">
<h3>{finding.title}</h3>
<p>{finding.summary}</p>
<div className="finding-stats">
<span>
<strong>{formatNumber(finding.credits)}</strong>
estimated credits
</span>
<span>
<strong>{finding.share.toFixed(1)}%</strong>
share
</span>
</div>
</div>
<div className="table-action-group">
<StatusBadge label={finding.severity} tone={finding.severity === 'High' ? 'red' : finding.severity === 'Medium' ? 'orange' : 'green'} />
<button
className="table-action-button"
type="button"
aria-label={`Review finding ${finding.rank}: ${finding.title}`}
onClick={() => onOpenFinding(finding.rank)}
>
<ArrowRight size={14} />
Review
</button>
</div>
</article>
))}
</div>
);
}

function recentCallsBasis(
shownCount: number,
visibleCount: number,
  runtime: OverviewRuntime,
  hasQuery: boolean,
): string {
  const rowScope = runtime.historyScope === 'all' || runtime.historyScope === 'all-history' ? 'all-history' : 'active-history';
  const loadLimitLabel = runtime.loadLimit === 0 ? 'no row cap' : `${formatNumber(runtime.loadLimit)} row request`;
  const loadedLabel = `${formatNumber(runtime.loadedRowCount)} loaded of ${formatNumber(runtime.totalAvailableRows)} available ${rowScope} rows`;
  const matchLabel = hasQuery ? `, ${formatNumber(visibleCount)} matching the current search` : '';
  return `Showing latest ${formatNumber(shownCount)} visible aggregate calls from ${loadedLabel}${matchLabel} (${loadLimitLabel}). Rows open Call Investigator.`;
}

function cacheCompositionCenterLabel(model: DashboardModel): string {
  const totalTokensCard = model.cards.find(card => card.label === 'Total Tokens');
  if (totalTokensCard?.value) return totalTokensCard.value;
  return formatCompact(model.calls.reduce((sum, call) => sum + call.totalTokens, 0));
}
