import {
  Activity,
  BarChart3,
  Columns3,
  Database,
  Download,
  Filter,
  LockKeyhole,
  RefreshCw,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import type { CallRow, DashboardModel } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { rowMatchesQuery, uniqueSorted } from '../shared/filtering';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import { callColumns, callCsvColumns } from '../shared/tables';

type CallsPageProps = {
  model: DashboardModel;
  globalQuery: string;
  onRefresh: () => void;
};

type DrillDownTab = 'summary' | 'tokens' | 'cache' | 'evidence';

const drillDownTabs: Array<{ id: DrillDownTab; label: string; icon: LucideIcon }> = [
  { id: 'summary', label: 'Summary', icon: Activity },
  { id: 'tokens', label: 'Tokens', icon: BarChart3 },
  { id: 'cache', label: 'Cache', icon: Database },
  { id: 'evidence', label: 'Evidence', icon: LockKeyhole },
];

export function CallsPage({ model, globalQuery, onRefresh }: CallsPageProps) {
  const [localQuery, setLocalQuery] = useState('');
  const [modelFilter, setModelFilter] = useState('all');
  const [effortFilter, setEffortFilter] = useState('all');
  const [density, setDensity] = useState<'dense' | 'roomy'>('dense');
  const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
  const [exportStatus, setExportStatus] = useState('');

  const modelOptions = useMemo(() => uniqueSorted(model.calls.map(call => call.model)), [model.calls]);
  const effortOptions = useMemo(() => uniqueSorted(model.calls.map(call => call.effort)), [model.calls]);
  const filteredCalls = useMemo(
    () =>
      model.calls.filter(call => {
        if (modelFilter !== 'all' && call.model !== modelFilter) {
          return false;
        }
        if (effortFilter !== 'all' && call.effort !== effortFilter) {
          return false;
        }
        const searchableValues = [call.thread, call.model, call.effort, call.signal, call.recommendation, call.rawTime, call.tags.join(' ')];
        return [globalQuery, localQuery].every(query => rowMatchesQuery(searchableValues, query));
      }),
    [effortFilter, globalQuery, localQuery, model.calls, modelFilter],
  );
  const selectedCall = filteredCalls.find(call => call.id === selectedCallId) ?? filteredCalls[0] ?? null;

  function exportCalls() {
    downloadCsv(`codex-calls-${csvDateStamp()}.csv`, rowsToCsv(filteredCalls, callCsvColumns));
    setExportStatus(`Exported ${filteredCalls.length} calls`);
  }

  return (
    <div className="page-grid">
      <div className="page-title-row">
        <div>
          <h1>Calls</h1>
          <p>High-density analyst view model calls, cost, cache hits, duration.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button" aria-label="Manage call columns">
            <Columns3 size={16} />
            Columns
          </button>
          <button className="toolbar-button" type="button" onClick={exportCalls} disabled={!filteredCalls.length}>
            <Download size={16} />
            Export
          </button>
          <button className="primary-button" type="button" onClick={onRefresh}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
      </div>
      <div className="dashboard-grid three">
        <Panel title="Usage Over Time" subtitle="Tokens">
          <LineChart series={model.tokenSeries} yLabel="Tokens" height={220} />
        </Panel>
        <Panel title="Cost by Model" subtitle="Estimated USD">
          <BarChart data={model.modelCosts} valueLabel={money} />
        </Panel>
        <Panel title="Cache Hit Rate Over Time" subtitle="Daily">
          <LineChart series={model.cacheSeries} yLabel="Cache %" height={220} valueFormatter={value => `${value}%`} />
        </Panel>
      </div>
      <div className="filter-row">
        <label className="search-box">
          <span className="sr-only">Search calls</span>
          <input value={localQuery} onChange={event => setLocalQuery(event.target.value)} placeholder="Search calls, threads, models..." />
        </label>
        <label className="filter-field">
          <span>Model</span>
          <select value={modelFilter} onChange={event => setModelFilter(event.target.value)}>
            <option value="all">All models</option>
            {modelOptions.map(option => (
              <option value={option} key={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <label className="filter-field">
          <span>Effort</span>
          <select value={effortFilter} onChange={event => setEffortFilter(event.target.value)}>
            <option value="all">All effort</option>
            {effortOptions.map(option => (
              <option value={option} key={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
        <button className="toolbar-button" type="button">
          <Filter size={16} />
          More Filters
        </button>
        <div className="density-toggle" aria-label="Density">
          <button type="button" className={density === 'dense' ? 'active' : ''} aria-pressed={density === 'dense'} onClick={() => setDensity('dense')}>
            Dense
          </button>
          <button type="button" className={density === 'roomy' ? 'active' : ''} aria-pressed={density === 'roomy'} onClick={() => setDensity('roomy')}>
            Roomy
          </button>
        </div>
      </div>
      <div className="table-detail-layout">
        <Panel
          title="Model Calls"
          subtitle={exportStatus || `Showing ${filteredCalls.length} of ${model.calls.length} aggregate rows`}
          action={<StatusBadge label="Raw context gated" tone="blue" />}
        >
          <DataTable
            columns={callColumns}
            data={filteredCalls}
            compact={density === 'dense'}
            getRowId={call => call.id}
            selectedRowId={selectedCall?.id}
            onRowSelect={call => setSelectedCallId(call.id)}
            ariaLabel="Model calls"
          />
        </Panel>
        <CallDrillDown call={selectedCall} />
      </div>
    </div>
  );
}

function CallDrillDown({ call }: { call: CallRow | null }) {
  const [activeTab, setActiveTab] = useState<DrillDownTab>('summary');

  if (!call) {
    return (
      <aside className="side-panel drilldown-panel">
        <Panel title="Call Drill-Down" subtitle="No matching call">
          <p className="empty-state">No aggregate row matches the active filters.</p>
        </Panel>
      </aside>
    );
  }

  return (
    <aside className="side-panel drilldown-panel">
      <Panel title="Call Drill-Down" subtitle={`${call.thread} / ${call.model}`}>
        <div className="call-summary">
          <StatusBadge label="Aggregate only" tone="green" />
          <StatusBadge label={call.signal} tone={call.signal === 'cache-risk' ? 'orange' : 'blue'} />
          <StatusBadge label="Raw context gated" tone="blue" />
          <span className="call-id">{call.id.slice(0, 12)}</span>
        </div>
        <div className="drilldown-tabs" role="tablist" aria-label="Call drill-down sections">
          {drillDownTabs.map(tab => {
            const Icon = tab.icon;
            const selected = activeTab === tab.id;
            return (
              <button
                type="button"
                role="tab"
                aria-selected={selected}
                className={selected ? 'active' : ''}
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <div className="drilldown-tab-panel" role="tabpanel">
          {activeTab === 'summary' ? <SummaryTab call={call} /> : null}
          {activeTab === 'tokens' ? <TokensTab call={call} /> : null}
          {activeTab === 'cache' ? <CacheTab call={call} /> : null}
          {activeTab === 'evidence' ? <EvidenceTab call={call} /> : null}
        </div>
      </Panel>
    </aside>
  );
}

function SummaryTab({ call }: { call: CallRow }) {
  return (
    <>
      <div className="drilldown-metric-grid">
        <DrillMetric label="Total tokens" value={formatNumber(call.totalTokens)} detail={`${formatCompact(call.input)} input`} />
        <DrillMetric label="Uncached input" value={formatNumber(call.uncachedInput)} detail="fresh billed input" />
        <DrillMetric label="Cache hit rate" value={pct(call.cachedPct)} detail={cacheState(call)} />
        <DrillMetric label="Estimated cost" value={money(call.cost)} detail={call.pricingEstimated ? 'estimated pricing' : 'configured pricing'} />
        <DrillMetric label="Duration" value={call.duration} detail={call.fast ? 'fast candidate' : 'normal throughput'} />
        <DrillMetric label="Usage credits" value={call.credits ? call.credits.toFixed(3) : '-'} detail={call.usageCreditConfidence} />
      </div>
      <TokenComposition call={call} />
      <CacheMiniChart call={call} />
      {call.recommendation ? (
        <div className="recommendation-box">
          <ShieldCheck size={16} />
          <p>{call.recommendation}</p>
        </div>
      ) : null}
    </>
  );
}

function TokensTab({ call }: { call: CallRow }) {
  const cachedInput = Math.max(call.input - call.uncachedInput, 0);
  return (
    <>
      <TokenComposition call={call} />
      <dl className="detail-list">
        <DetailRow label="Input tokens" value={formatNumber(call.input)} />
        <DetailRow label="Cached input" value={formatNumber(cachedInput)} />
        <DetailRow label="Uncached input" value={formatNumber(call.uncachedInput)} />
        <DetailRow label="Output tokens" value={formatNumber(call.output)} />
        <DetailRow label="Reasoning output" value={formatNumber(call.reasoningOutput)} />
        <DetailRow label="Total tokens" value={formatNumber(call.totalTokens)} />
      </dl>
    </>
  );
}

function CacheTab({ call }: { call: CallRow }) {
  return (
    <>
      <CacheMiniChart call={call} />
      <dl className="detail-list">
        <DetailRow label="Cache state" value={cacheState(call)} />
        <DetailRow label="Cache hit rate" value={pct(call.cachedPct)} />
        <DetailRow label="Fresh share" value={pct(Math.max(100 - call.cachedPct, 0))} />
        <DetailRow label="Signal" value={call.signal} />
      </dl>
      <p className="privacy-note">Use this readout to decide whether the aggregate call needs deeper raw-context investigation.</p>
    </>
  );
}

function EvidenceTab({ call }: { call: CallRow }) {
  return (
    <>
      <div className="locked-context-card">
        <LockKeyhole size={20} />
        <div>
          <strong>Raw context is gated</strong>
          <p>Prompt text, assistant text, and tool output are not embedded. Evidence can load only through the explicit localhost context API.</p>
        </div>
      </div>
      <dl className="detail-list">
        <DetailRow label="Record id" value={call.id} />
        <DetailRow label="Time" value={call.time} />
        <DetailRow label="Thread" value={call.thread} />
        <DetailRow label="Model" value={call.model} />
        <DetailRow label="Effort" value={call.effort} />
      </dl>
      <div className="action-row">
        <button className="primary-button" type="button" disabled>
          Open investigator
        </button>
        <button className="toolbar-button" type="button" disabled>
          Show turn evidence
        </button>
      </div>
      <p className="privacy-note">These actions are intentionally disabled until `/api/context` is wired with explicit raw-context permission.</p>
    </>
  );
}

function DrillMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <span className="drilldown-metric">
      <small>{label}</small>
      <strong>{value}</strong>
      <em>{detail}</em>
    </span>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function TokenComposition({ call }: { call: CallRow }) {
  const cachedInput = Math.max(call.input - call.uncachedInput, 0);
  const segments = [
    { label: 'Cached input', value: cachedInput, color: '#2563eb' },
    { label: 'Uncached input', value: call.uncachedInput, color: '#f59e0b' },
    { label: 'Output', value: call.output, color: '#059669' },
    { label: 'Reasoning', value: call.reasoningOutput, color: '#7c3aed' },
  ].filter(segment => segment.value > 0);
  const total = Math.max(
    segments.reduce((sum, segment) => sum + segment.value, 0),
    1,
  );

  return (
    <div className="composition-card">
      <div className="composition-head">
        <strong>Token composition</strong>
        <span>{formatCompact(total)} visible tokens</span>
      </div>
      <div className="composition-bar" aria-label="Token composition">
        {segments.map(segment => (
          <i key={segment.label} style={{ width: `${Math.max(segment.value / total * 100, 3)}%`, background: segment.color }} />
        ))}
      </div>
      <div className="composition-legend">
        {segments.map(segment => (
          <span key={segment.label}>
            <i style={{ background: segment.color }} />
            {segment.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function CacheMiniChart({ call }: { call: CallRow }) {
  const bars = [
    { label: 'Cache', value: Math.min(Math.max(call.cachedPct, 0), 100), color: '#2563eb' },
    { label: 'Fresh', value: Math.min(Math.max(100 - call.cachedPct, 0), 100), color: '#f59e0b' },
    { label: 'Output', value: Math.min(Math.max(call.output / Math.max(call.totalTokens, 1) * 100, 0), 100), color: '#059669' },
  ];

  return (
    <div className="cache-mini-card">
      <div>
        <strong>Cache delta readout</strong>
        <span>{cacheState(call)}</span>
      </div>
      <div className="cache-bars" aria-label="Cache delta readout">
        {bars.map(bar => (
          <span key={bar.label}>
            <i style={{ height: `${Math.max(bar.value, 4)}%`, background: bar.color }} />
            <em>{bar.label}</em>
          </span>
        ))}
      </div>
    </div>
  );
}

function cacheState(call: CallRow): string {
  if (call.cachedPct < 25) {
    return 'cold or weak cache';
  }
  if (call.cachedPct < 50) {
    return 'partial cache reuse';
  }
  return 'healthy cache reuse';
}
