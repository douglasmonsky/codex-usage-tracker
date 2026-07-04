import type { ColumnDef } from '@tanstack/react-table';
import { Copy, RefreshCw, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { CallRow, DashboardModel } from '../../api/types';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { MetricCard } from '../../components/MetricCard';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { uniqueSorted } from '../shared/filtering';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import { callActionColumn, callInvestigatorRowLabel, weeklyColumns } from '../shared/tables';

type UsageDrainPageProps = {
  model: DashboardModel;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

type ConfidenceFilter = '0.70' | '0.55';
type UsageDrainControls = {
  planFilter: string;
  effortFilter: string;
  includeSubagents: boolean;
  minSampleSize: number;
  confidenceFilter: ConfidenceFilter;
};

type DrainEvidenceBasis = {
  selection: string;
  ordering: string;
  limit: string;
  summary: string;
};

const DEFAULT_MIN_SAMPLE_SIZE = 20;

export function usageDrainCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  return usageDrainEvidenceCalls(model.calls, usageDrainControlsFromUrl());
}

export function UsageDrainPage({ model, onOpenInvestigator, onCopyCallLink }: UsageDrainPageProps) {
  const initialControls = usageDrainControlsFromUrl();
  const [refreshStatus, setRefreshStatus] = useState('Snapshot loaded');
  const [planFilter, setPlanFilter] = useState(initialControls.planFilter);
  const [effortFilter, setEffortFilter] = useState(initialControls.effortFilter);
  const [includeSubagents, setIncludeSubagents] = useState(initialControls.includeSubagents);
  const [minSampleSize, setMinSampleSize] = useState(initialControls.minSampleSize);
  const [confidenceFilter, setConfidenceFilter] = useState<ConfidenceFilter>(initialControls.confidenceFilter);

  const planOptions = useMemo(
    () => uniqueSorted([...model.weeklyWindows.map(window => window.plan), planFilter].filter(option => option !== 'all')),
    [model.weeklyWindows, planFilter],
  );
  const effortOptions = useMemo(
    () => uniqueSorted([...model.calls.map(call => call.effort), effortFilter].filter(option => option !== 'all')),
    [effortFilter, model.calls],
  );
  const filteredWeeklyWindows = useMemo(
    () =>
      model.weeklyWindows.filter(window => {
        if (planFilter !== 'all' && window.plan !== planFilter) return false;
        if (confidenceFilter === '0.70') return window.confidence === 'High';
        return window.confidence === 'High' || window.confidence === 'Medium';
      }),
    [confidenceFilter, model.weeklyWindows, planFilter],
  );
  const drainCalls = useMemo(
    () => usageDrainEvidenceCalls(model.calls, { planFilter, effortFilter, includeSubagents, minSampleSize, confidenceFilter }),
    [confidenceFilter, effortFilter, includeSubagents, minSampleSize, model.calls, planFilter],
  );
  const topEvidenceCalls = drainCalls.slice(0, 8);
  const evidenceSummary = summarizeDrainEvidence(drainCalls);
  const evidenceBasis = drainEvidenceBasis(effortFilter, includeSubagents, minSampleSize);
  const evidenceColumns = useMemo<Array<ColumnDef<CallRow>>>(
    () => [
      { accessorKey: 'time', header: 'Time' },
      { accessorKey: 'thread', header: 'Thread' },
      { accessorKey: 'model', header: 'Model' },
      {
        accessorKey: 'effort',
        header: 'Effort',
        cell: info => <span className={`pill effort-${String(info.getValue())}`}>{String(info.getValue())}</span>,
      },
      {
        id: 'credits',
        header: 'Credits',
        cell: info => <span className="num">{formatCompact(callCredits(info.row.original))}</span>,
        sortingFn: (left, right) => callCredits(left.original) - callCredits(right.original),
      },
      {
        accessorKey: 'cost',
        header: 'Est. Cost',
        cell: info => <span className="num">{money(Number(info.getValue()))}</span>,
      },
      {
        accessorKey: 'cachedPct',
        header: 'Cached %',
        cell: info => <span className="cache-pill">{pct(Number(info.getValue()))}</span>,
      },
      callActionColumn({ onOpenInvestigator, onCopyCallLink, labelPrefix: 'usage drain call' }),
    ],
    [onCopyCallLink, onOpenInvestigator],
  );

  function refreshDiagnostics() {
    setRefreshStatus(
      `Diagnostics refreshed ${new Intl.DateTimeFormat('en-US', { hour: 'numeric', minute: '2-digit' }).format(new Date())}`,
    );
  }

  function syncControls(next: Partial<UsageDrainControls>) {
    syncUsageDrainUrl({ planFilter, effortFilter, includeSubagents, minSampleSize, confidenceFilter, ...next });
  }

  return (
    <div className="lab-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Usage Drain Lab</h1>
          <p>Weekly credits, visible usage remaining, model controls, fast-mode proxy signals.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label="Local Only" tone="green" />
          <StatusBadge label={refreshStatus} tone="blue" />
          <button className="primary-button" type="button" onClick={refreshDiagnostics}>
            <RefreshCw size={16} />
            Refresh Diagnostics
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
          <LineChart
            series={model.usageRemainingSeries}
            yLabel="Percent remaining"
            valueFormatter={value => `${value}%`}
          />
        </Panel>
        <Panel title="Token-Derived Credits vs Visible Usage Drain" subtitle="Correlation view for Pro windows">
          <LineChart series={model.actualVsPredictedSeries} yLabel="Credits" />
        </Panel>
        <Panel
          title="Weekly Windows"
          subtitle={`Showing ${filteredWeeklyWindows.length} of ${model.weeklyWindows.length} windows`}
        >
          <DataTable columns={weeklyColumns} data={filteredWeeklyWindows} compact ariaLabel="Usage drain weekly windows" />
        </Panel>
        <Panel
          title="Usage Drain Evidence Calls"
          subtitle={`Top ${topEvidenceCalls.length} aggregate calls - ${evidenceBasis.summary}`}
          action={<StatusBadge label="Rows open investigator" tone="green" />}
        >
          <DataTable
            columns={evidenceColumns}
            data={topEvidenceCalls}
            compact
            emptyLabel="No loaded aggregate calls match the usage drain controls."
getRowId={call => call.id}
getRowActionLabel={call => callInvestigatorRowLabel(call, 'usage drain evidence call')}
onRowActivate={call => onOpenInvestigator(call.id)}
            ariaLabel="Usage drain evidence calls"
          />
        </Panel>
      </div>

      <aside className="side-panel">
        <Panel title="Model / Effort Controls">
          <div className="form-grid">
            <label>
              Plan
              <select
                value={planFilter}
                onChange={event => {
                  const next = event.target.value;
                  setPlanFilter(next);
                  syncControls({ planFilter: next });
                }}
              >
                <option value="all">All plans</option>
                {planOptions.map(option => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Effort Filter
              <select
                value={effortFilter}
                onChange={event => {
                  const next = event.target.value;
                  setEffortFilter(next);
                  syncControls({ effortFilter: next });
                }}
              >
                <option value="all">All efforts</option>
                {effortOptions.map(option => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <label className="toggle-row">
              <input
                type="checkbox"
                checked={includeSubagents}
                onChange={event => {
                  const next = event.target.checked;
                  setIncludeSubagents(next);
                  syncControls({ includeSubagents: next });
                }}
              />
              Include subagents
            </label>
          </div>
        </Panel>

        <Panel title="Fast Mode Analysis">
          <div className="form-grid">
            <label>
              Min sample size
              <input
                type="number"
                min={1}
                value={minSampleSize}
                onChange={event => {
                  const next = Math.max(1, Number(event.target.value) || 1);
                  setMinSampleSize(next);
                  syncControls({ minSampleSize: next });
                }}
              />
            </label>
            <label>
              Confidence threshold
              <select
                value={confidenceFilter}
                onChange={event => {
                  const next = event.target.value === '0.55' ? '0.55' : '0.70';
                  setConfidenceFilter(next);
                  syncControls({ confidenceFilter: next });
                }}
              >
                <option value="0.70">0.70 High</option>
                <option value="0.55">0.55 Medium</option>
              </select>
            </label>
            <StatusBadge
              label={drainCalls.length >= minSampleSize ? 'Sample ready' : 'Below min sample'}
              tone={drainCalls.length >= minSampleSize ? 'green' : 'orange'}
            />
          </div>
        </Panel>

        <Panel title="Drain Evidence Profile" subtitle={`${drainCalls.length} calls in active sample`}>
          <div className="evidence-list">
            <span>
              Credits <strong>{formatCompact(evidenceSummary.credits)}</strong>
            </span>
            <span>
              Est. cost <strong>{money(evidenceSummary.cost)}</strong>
            </span>
            <span>
              Avg cache <strong>{pct(evidenceSummary.avgCachePct)}</strong>
            </span>
            <span>
              High effort <strong>{formatNumber(evidenceSummary.highEffortCount)}</strong>
            </span>
          </div>
          <div className="finding-module">
            <h3>Evidence Basis</h3>
            <ul className="compact-list">
              <li>Selection: {evidenceBasis.selection}</li>
              <li>Order: {evidenceBasis.ordering}</li>
              <li>Limit: {evidenceBasis.limit}</li>
            </ul>
          </div>

          <div className="finding-module">
            <div className="section-heading compact">
              <h3>Top Evidence Calls</h3>
              <span>{topEvidenceCalls.length ? 'Open any row' : 'No matches'}</span>
            </div>
            {topEvidenceCalls.length ? (
              <ol className="thread-mini-timeline">
                {topEvidenceCalls.slice(0, 4).map(call => (
                  <li
                    key={call.id}
                    className="thread-call-row has-row-action"
                    tabIndex={0}
                    aria-label={`Open investigator usage drain evidence call ${call.thread} ${call.model}`}
                    onClick={() => onOpenInvestigator(call.id)}
                    onKeyDown={event => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onOpenInvestigator(call.id);
                      }
                    }}
                  >
                    <span>{call.time}</span>
                    <strong>{call.thread}</strong>
                    <em>
                      {formatCompact(callCredits(call))} credits - {call.model} / {call.effort}
                    </em>
                    <div className="thread-call-actions table-action-group">
                      <button
                        className="table-action-button"
                        type="button"
                        aria-label={`Open investigator for usage drain evidence call ${call.thread} ${call.model}`}
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
                        aria-label={`Copy link for usage drain evidence call ${call.thread} ${call.model}`}
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
              <p className="empty-state">No loaded aggregate calls match the current controls.</p>
            )}
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

function callCredits(call: CallRow): number {
  return call.credits > 0 ? call.credits : call.cost * 25;
}

function usageDrainEvidenceCalls(calls: CallRow[], controls: UsageDrainControls): CallRow[] {
  return [...calls]
    .filter(call => {
      if (controls.effortFilter !== 'all' && call.effort !== controls.effortFilter) return false;
      if (!controls.includeSubagents && call.tags.includes('subagent')) return false;
      return true;
    })
    .sort((left, right) => callCredits(right) - callCredits(left) || right.totalTokens - left.totalTokens)
    .slice(0, Math.max(controls.minSampleSize, 1));
}

function usageDrainControlsFromUrl(): UsageDrainControls {
  const params = new URLSearchParams(window.location.search);
  const plan = params.get('usage_plan')?.trim() ?? 'all';
  const effort = params.get('usage_effort')?.trim() ?? 'all';
  const subagents = params.get('usage_subagents');

  return {
    planFilter: plan || 'all',
    effortFilter: effort || 'all',
    includeSubagents: subagents === '0' || subagents === 'false' ? false : true,
    minSampleSize: sampleSizeFromUrl(params.get('usage_sample')),
    confidenceFilter: params.get('usage_confidence') === '0.55' ? '0.55' : '0.70',
  };
}

function sampleSizeFromUrl(value: string | null): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.round(parsed) : DEFAULT_MIN_SAMPLE_SIZE;
}

function syncUsageDrainUrl(controls: UsageDrainControls) {
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'usage-drain');
  setOrDeleteParam(url, 'usage_plan', controls.planFilter, 'all');
  setOrDeleteParam(url, 'usage_effort', controls.effortFilter, 'all');
  setOrDeleteParam(url, 'usage_subagents', controls.includeSubagents ? '1' : '0', '1');
  setOrDeleteParam(url, 'usage_sample', String(Math.max(controls.minSampleSize, 1)), String(DEFAULT_MIN_SAMPLE_SIZE));
  setOrDeleteParam(url, 'usage_confidence', controls.confidenceFilter, '0.70');
  window.history.replaceState(null, '', url);
}

function setOrDeleteParam(url: URL, key: string, value: string, defaultValue: string) {
  if (value === defaultValue) {
    url.searchParams.delete(key);
    return;
  }
  url.searchParams.set(key, value);
}

function drainEvidenceBasis(effortFilter: string, includeSubagents: boolean, minSampleSize: number): DrainEvidenceBasis {
  const effortScope = effortFilter === 'all' ? 'all efforts' : `${effortFilter} effort`;
  const subagentScope = includeSubagents ? 'including subagents' : 'excluding subagents';
  const sampleSize = Math.max(minSampleSize, 1);
  return {
    selection: `${effortScope}, ${subagentScope}`,
    ordering: 'estimated Codex credits descending, then total tokens',
    limit: `active sample top ${sampleSize.toLocaleString()} calls; table shows first 8`,
    summary: `${effortScope}, sorted by estimated credits`,
  };
}

function summarizeDrainEvidence(calls: CallRow[]) {
  const count = calls.length;
  return {
    credits: calls.reduce((sum, call) => sum + callCredits(call), 0),
    cost: calls.reduce((sum, call) => sum + call.cost, 0),
    avgCachePct: count ? calls.reduce((sum, call) => sum + call.cachedPct, 0) / count : 0,
    highEffortCount: calls.filter(call => call.effort.toLowerCase() === 'high').length,
  };
}
