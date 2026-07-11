import { Copy, Search } from 'lucide-react';
import { useMemo, useState, type CSSProperties } from 'react';

import type { CallRow, ContextRuntime, DashboardModel, HeatmapRow, ThreadRow } from '../../api/types';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { MetricCard } from '../../components/MetricCard';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import { threadActionColumn, threadColumns, threadInvestigatorRowLabel } from '../shared/tables';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';
import { useCacheContextEvidence } from './cacheContextEvidence';

type CacheContextPageProps = {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  includeArchived?: boolean;
  scopeSince?: string | null;
  sourceRevision?: string;
  focusedEndpointsEnabled?: boolean;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

export function cacheContextCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  const selectedThread = cacheThreadFromUrl(model.threads) ?? model.threads[0] ?? null;
  return cacheThreadCalls(model.calls, selectedThread);
}

export function CacheContextPage({
  model,
  contextRuntime,
  includeArchived = false,
  scopeSince = null,
  sourceRevision = '',
  focusedEndpointsEnabled = import.meta.env.MODE !== 'test',
  onOpenInvestigator,
  onCopyCallLink,
}: CacheContextPageProps) {
  const [selectedThreadName, setSelectedThreadName] = useState<string | null>(cacheThreadParam);
  const evidence = useCacheContextEvidence({
    model,
    runtime: contextRuntime,
    includeArchived,
    scopeSince,
    selectedThreadName,
    sourceRevision,
    enabled: focusedEndpointsEnabled,
  });
  const selectedThread = evidence.selectedThread;
  const threadTableColumns = useMemo(
    () => [...threadColumns, threadActionColumn({ onOpenInvestigator, onCopyCallLink })],
    [onCopyCallLink, onOpenInvestigator],
  );
  const selectedCalls = evidence.selectedCalls;
const selectedHeatmap = selectedThread
? evidence.heatmap.find(row => threadLabelsMatch(row.thread, selectedThread.name))
: null;
const heatmapWindowLabels = useMemo(() => cacheHeatmapWindowLabels(evidence.heatmap), [evidence.heatmap]);

return (
    <div className="cache-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Cache And Context Lab</h1>
          <p>Cache behavior, cold resumes, context pressure, optimization recommendations.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label={evidence.usingFocusedEndpoints ? 'Full-scope endpoints' : 'Snapshot fallback'} tone={evidence.usingFocusedEndpoints ? 'green' : 'orange'} />
          <StatusBadge label="Context safe" tone="blue" />
        </div>
      </div>

      <div className="metric-grid span-all">
        {evidence.cards.map(card => (
          <MetricCard key={card.label} card={card} />
        ))}
      </div>

      <Panel title="Cache Hit Rate & Context Window Over Time" subtitle="Cache reuse and context pressure">
        <LineChart
          series={[...evidence.cacheSeries, model.usageRemainingSeries[0]].filter(Boolean)}
          yLabel="Percent"
          valueFormatter={value => `${value}%`}
        />
      </Panel>

<Panel title="Cache Reuse Heatmap" subtitle={heatmapWindowLabels.length ? `${heatmapWindowLabels.length} cache windows` : 'No cache heatmap rows'}>
        {heatmapWindowLabels.length ? (
          <div className="heatmap-scroll" tabIndex={0} aria-label="Scrollable cache reuse heatmap">
            <div className="heatmap" role="table" aria-label="Cache reuse heatmap" style={{ '--heatmap-columns': heatmapWindowLabels.length } as CSSProperties}>
              <div className="heatmap-head" role="row">
                <span className="sticky-column" role="columnheader">Thread</span>
                {heatmapWindowLabels.map(label => (
                  <span key={label} role="columnheader">{label}</span>
                ))}
              </div>
              {evidence.heatmap.map(row => (
                <div className="heatmap-row" role="row" key={row.thread}>
                  <strong className="sticky-column" role="rowheader">{row.thread}</strong>
                  {heatmapWindowLabels.map((label, index) => {
                    const value = row.values[index];
                    return (
                      <span role="cell" key={`${row.thread}-${label}`} style={{ '--intensity': (value ?? 0) / 100 } as CSSProperties}>
                        {typeof value === 'number' ? `${value}%` : '-'}
                      </span>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="empty-state">No cache heatmap rows in the current aggregate snapshot.</p>
        )}
      </Panel>

      <Panel
        title="Threads Overview"
        subtitle={
          selectedThread
            ? `Selected ${selectedThread.name}: ${pct(selectedThread.cachePct)} cache`
            : 'Cold resume and cache efficiency signals'
        }
        className="span-all"
        action={<StatusBadge label="Hover previews; rows open latest call" tone="green" />}
      >
        <DataTable
          columns={threadTableColumns}
          data={evidence.threads}
          compact
getRowId={thread => thread.name}
getRowActionLabel={threadInvestigatorRowLabel}
selectedRowId={selectedThread?.name}
          onRowSelect={thread => {
            setSelectedThreadName(thread.name);
            syncCacheThreadUrl(thread.name);
          }}
          onRowActivate={thread => {
            if (thread.latestCallId) {
onOpenInvestigator(thread.latestCallId);
}
}}
activateOnClick
selectOnHover
ariaLabel="Cache context threads overview"
/>
        <p className="table-caption">Showing {formatNumber(evidence.threads.length)} of {formatNumber(evidence.totalThreads)} full-scope thread summaries.</p>
      </Panel>

<SelectedCacheThreadPanel
        selectedThread={selectedThread}
        heatmap={selectedHeatmap}
        heatmapWindowLabels={heatmapWindowLabels}
        calls={selectedCalls}
        onOpenInvestigator={onOpenInvestigator}
        onCopyCallLink={onCopyCallLink}
      />
    </div>
  );
}

function SelectedCacheThreadPanel({
selectedThread,
heatmap,
heatmapWindowLabels,
  calls,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  selectedThread: ThreadRow | null;
  heatmap: HeatmapRow | null | undefined;
  heatmapWindowLabels: string[];
  calls: CallRow[];
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  if (!selectedThread) {
    return (
      <aside className="side-panel">
        <Panel title="Selected Thread Diagnosis" subtitle="No matching thread">
          <p className="empty-state">No grouped thread is available in the current aggregate snapshot.</p>
        </Panel>
      </aside>
    );
  }

  return (
    <aside className="side-panel">
      <Panel title="Selected Thread Diagnosis" subtitle={selectedThread.name}>
        <div className="finding-module">
          <div className="section-heading compact">
            <h3>Efficiency Profile</h3>
            <span>{selectedThread.coldResumeRisk} risk</span>
          </div>
          <div className="evidence-list">
            <span>
              Turns <strong>{formatNumber(selectedThread.turns)}</strong>
            </span>
            <span>
              Tokens <strong>{formatCompact(selectedThread.totalTokens)}</strong>
            </span>
            <span>
              Cache hit <strong>{pct(selectedThread.cachePct)}</strong>
            </span>
            <span>
              Est. cost <strong>{money(selectedThread.cost)}</strong>
            </span>
            <span>
              Cost/call <strong>{money(selectedThread.costPerCall)}</strong>
            </span>
          </div>
        </div>

        <div className="finding-module">
          <div className="section-heading compact">
            <h3>Cache Windows</h3>
            <span>{heatmap ? 'Weekly reuse' : 'No heatmap row'}</span>
          </div>
          {heatmap ? (
            <div className="cache-window-strip" aria-label={`Cache windows for ${selectedThread.name}`}>
{cacheWindowLabelsForRow(heatmap, heatmapWindowLabels).map((label, index) => {
const value = heatmap.values[index];
return (
<span key={`${selectedThread.name}-window-${label}`} style={{ '--intensity': (value ?? 0) / 100 } as CSSProperties}>
<small>{label}</small>
<strong>{typeof value === 'number' ? `${value}%` : '-'}</strong>
</span>
);
})}
            </div>
          ) : (
            <p className="empty-state">No weekly cache heatmap row matches this selected thread.</p>
          )}
        </div>

        <div className="finding-module">
          <div className="section-heading compact">
            <h3>Thread Calls</h3>
            <span>{calls.length ? `${calls.length} loaded` : 'No loaded calls'}</span>
          </div>
          {calls.length ? (
            <ol className="thread-mini-timeline">
              {calls.slice(0, 5).map(call => (
                <li
                  key={call.id}
                  className="thread-call-row has-row-action"
                  tabIndex={0}
                  aria-label={`Open investigator for cache thread call ${call.thread} ${call.model}`}
                  onClick={() => onOpenInvestigator(call.id)}
                  onKeyDown={event => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onOpenInvestigator(call.id);
                    }
                  }}
                >
                  <span>{call.time}</span>
                  <strong>{call.model} / {call.effort}</strong>
                  <em>
                    {formatCompact(call.totalTokens)} tokens - {pct(call.cachedPct)} cache
                  </em>
 <div className="thread-call-actions table-action-group">
 <button
 className="table-action-button"
 type="button"
 aria-label={`Open investigator for cache thread call ${call.thread} ${call.model}`}
 onKeyDown={stopRowActionKeyDown}
 onClick={event => {
 event.stopPropagation();
 onOpenInvestigator(call.id);
 }}
 >
 <Search size={14} />
 Open
 </button>
 <button
 className="table-action-button"
 type="button"
 aria-label={`Copy link for cache thread call ${call.thread} ${call.model}`}
 onKeyDown={stopRowActionKeyDown}
 onClick={event => {
 event.stopPropagation();
 onCopyCallLink(call.id);
 }}
 >
 <Copy size={14} />
 Copy
 </button>
 </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="empty-state">No loaded aggregate call rows match this selected thread.</p>
          )}
      </div>

      <div className="finding-module">
        <h3>Diagnosis Basis</h3>
        <ul className="compact-list">
          <li>Risk: {selectedThread.coldResumeRisk} cold-resume score</li>
          <li>Cache: {pct(selectedThread.cachePct)} hit rate; action threshold below 35%</li>
          <li>Cost: {money(selectedThread.costPerCall)} per call; inspect threshold above $1.00</li>
          <li>Evidence: {calls.length} loaded calls, {heatmap ? `${heatmap.values.length} cache windows` : 'no heatmap row'}</li>
        </ul>
      </div>

      <div className="finding-module">
        <h3>Suggested Actions</h3>
          <ul className="compact-list">
            {suggestedCacheActions(selectedThread).map(action => (
              <li key={action}>{action}</li>
            ))}
          </ul>
        </div>
      </Panel>
    </aside>
  );
}

function suggestedCacheActions(thread: ThreadRow): string[] {
  const actions = [];
  if (thread.coldResumeRisk === 'High') {
    actions.push('Summarize before the next work session.');
  }
  if (thread.cachePct < 35) {
    actions.push('Split completed topics or reduce repeated uncached context.');
  }
  if (thread.costPerCall > 1) {
    actions.push('Open a related call and inspect whether model effort was justified.');
  }
  if (!actions.length) {
    actions.push('Keep the thread warm and continue monitoring cache reuse.');
  }
  return actions;
}

function cacheThreadCalls(calls: CallRow[], thread: ThreadRow | null): CallRow[] {
  return thread ? calls.filter(call => threadLabelsMatch(call.thread, thread.name)).sort(compareCallTimeDescending) : [];
}

function cacheThreadNameFromUrl(threads: ThreadRow[]): string | null {
  const threadName = cacheThreadParam();
  if (!threadName) return null;
  return threads.some(thread => thread.name === threadName) ? threadName : null;
}

function cacheThreadParam(): string | null {
  return new URLSearchParams(window.location.search).get('cache_thread')?.trim() || null;
}

function cacheThreadFromUrl(threads: ThreadRow[]): ThreadRow | null {
  const threadName = cacheThreadNameFromUrl(threads);
  return threadName ? threads.find(thread => thread.name === threadName) ?? null : null;
}

function syncCacheThreadUrl(threadName: string) {
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'cache-context');
  url.searchParams.set('cache_thread', threadName);
  window.history.replaceState(null, '', url);
}

function compareCallTimeDescending(left: CallRow, right: CallRow): number {
  return Date.parse(right.rawTime || right.time) - Date.parse(left.rawTime || left.time);
}

function threadLabelsMatch(callThread: string, threadName: string): boolean {
  const callLabel = callThread.trim();
  const summaryLabel = threadName.trim();
  return callLabel === summaryLabel || callLabel.startsWith(summaryLabel) || summaryLabel.startsWith(callLabel);
}

function cacheHeatmapWindowLabels(rows: HeatmapRow[]): string[] {
const labelledRow = rows.find(row => row.labels?.length);
const windowCount = rows.reduce((count, row) => Math.max(count, row.values.length, row.labels?.length ?? 0), 0);
return Array.from({ length: windowCount }, (_, index) => labelledRow?.labels?.[index] ?? `Window ${index + 1}`);
}

function cacheWindowLabelsForRow(row: HeatmapRow, fallbackLabels: string[]): string[] {
if (row.labels?.length) return cacheHeatmapWindowLabels([row]);
const windowCount = Math.max(row.values.length, fallbackLabels.length);
return Array.from({ length: windowCount }, (_, index) => fallbackLabels[index] ?? `Window ${index + 1}`);
}
