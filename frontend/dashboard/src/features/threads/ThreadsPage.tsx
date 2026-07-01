import { Columns3, Download, Filter } from 'lucide-react';
import { useMemo, useState } from 'react';
import type { DashboardModel, ThreadRow } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { DonutChart } from '../../charts/DonutChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { rowMatchesQuery } from '../shared/filtering';
import { formatCompact, money, pct } from '../shared/format';
import { threadColumns, threadCsvColumns } from '../shared/tables';

type ThreadsPageProps = {
  model: DashboardModel;
  globalQuery: string;
};

export function ThreadsPage({ model, globalQuery }: ThreadsPageProps) {
  const [localQuery, setLocalQuery] = useState('');
  const [riskFilter, setRiskFilter] = useState('all');
  const [selectedThreadName, setSelectedThreadName] = useState<string | null>(null);
  const [exportStatus, setExportStatus] = useState('');

  const filteredThreads = useMemo(
    () =>
      model.threads.filter(thread => {
        if (riskFilter !== 'all' && thread.coldResumeRisk !== riskFilter) {
          return false;
        }
        const searchableValues = [thread.name, thread.coldResumeRisk, thread.totalTokens, thread.cost, thread.cachePct];
        return [globalQuery, localQuery].every(query => rowMatchesQuery(searchableValues, query));
      }),
    [globalQuery, localQuery, model.threads, riskFilter],
  );
  const selected = filteredThreads.find(thread => thread.name === selectedThreadName) ?? filteredThreads[0] ?? null;

  function exportThreads() {
    downloadCsv(`codex-threads-${csvDateStamp()}.csv`, rowsToCsv(filteredThreads, threadCsvColumns));
    setExportStatus(`Exported ${filteredThreads.length} threads`);
  }

  return (
    <div className="thread-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Thread Efficiency</h1>
          <p>Threads as units of work, with cost concentration and handoff signals.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button" onClick={exportThreads} disabled={!filteredThreads.length}>
            <Download size={16} />
            Export
          </button>
          <button className="toolbar-button" type="button">
            <Filter size={16} />
            Filters
          </button>
          <button className="toolbar-button" type="button" aria-label="Manage thread columns">
            <Columns3 size={16} />
            Columns
          </button>
        </div>
      </div>
      <div className="filter-row span-all">
        <label className="search-box">
          <span className="sr-only">Search threads</span>
          <input value={localQuery} onChange={event => setLocalQuery(event.target.value)} placeholder="Search threads, risks, token totals..." />
        </label>
        <label className="filter-field">
          <span>Cold risk</span>
          <select value={riskFilter} onChange={event => setRiskFilter(event.target.value)}>
            <option value="all">All risks</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </label>
      </div>
      <Panel title="Cost vs Turns" subtitle="Sorted by estimated cost">
        <BarChart
          data={filteredThreads.map(thread => ({
            label: thread.name,
            value: thread.cost,
            color: thread.cachePct < 20 ? '#ef4444' : thread.cachePct < 45 ? '#f59e0b' : '#16a34a',
          }))}
          valueLabel={money}
        />
      </Panel>
      <Panel
        title="Thread Leaderboard"
        subtitle={exportStatus || `Showing ${filteredThreads.length} of ${model.threads.length} grouped threads`}
        action={<StatusBadge label={globalQuery || localQuery ? 'Filtered' : 'Aggregate'} tone="blue" />}
      >
        <DataTable
          columns={threadColumns}
          data={filteredThreads}
          compact
          getRowId={thread => thread.name}
          selectedRowId={selected?.name}
          onRowSelect={thread => setSelectedThreadName(thread.name)}
          ariaLabel="Thread leaderboard"
        />
      </Panel>
      <ThreadDetail selected={selected} />
    </div>
  );
}

function ThreadDetail({ selected }: { selected: ThreadRow | null }) {
  if (!selected) {
    return (
      <aside className="side-panel">
        <Panel title="Selected Thread" subtitle="No matching thread">
          <p className="empty-state">No grouped thread matches the active filters.</p>
        </Panel>
      </aside>
    );
  }

  return (
    <aside className="side-panel">
      <Panel title="Selected Thread" subtitle={selected.name}>
        <div className="detail-stat-grid vertical">
          <span>
            <strong>{selected.turns}</strong>
            Turns visible
          </span>
          <span>
            <strong>{money(selected.cost)}</strong>
            Estimated cost
          </span>
          <span>
            <strong>{pct(selected.cachePct)}</strong>
            Cache hit rate
          </span>
          <span>
            <strong>{formatCompact(selected.totalTokens)}</strong>
            Total tokens
          </span>
        </div>
        <DonutChart
          centerLabel="Risk Mix"
          data={[
            { label: 'Cold risk', value: selected.coldResumeRisk === 'High' ? 55 : selected.coldResumeRisk === 'Medium' ? 35 : 15, color: '#f59e0b' },
            { label: 'Cache reuse', value: selected.cachePct, color: '#2563eb' },
            { label: 'Productivity', value: selected.productivity, color: '#059669' },
          ]}
        />
      </Panel>
    </aside>
  );
}
