import type { ColumnDef } from '@tanstack/react-table';
import { ArrowRight, Copy, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { CallRow, DashboardModel, Finding } from '../../api/types';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import { callActionColumn, callColumns, callInvestigatorRowLabel } from '../shared/tables';

type InvestigatorPageProps = {
  model: DashboardModel;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

type EvidenceProfile = {
  callCount: number;
  totalTokens: number;
  avgCachePct: number;
  estimatedCost: number;
  modelCount: number;
};

type EvidenceBasis = {
  selection: string;
  ordering: string;
  limit: string;
  summary: string;
};

export function investigatorCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  const selected = findingFromUrl(model.findings);
  return selected ? callsForFinding(selected, model.calls) : topCalls(model.calls, 8);
}

export function InvestigatorPage({ model, onOpenInvestigator, onCopyCallLink }: InvestigatorPageProps) {
  const [selectedRank, setSelectedRank] = useState(() => findingFromUrl(model.findings)?.rank ?? model.findings[0]?.rank ?? 0);
  const [evidenceStatus, setEvidenceStatus] = useState('Select a finding to inspect aggregate evidence.');
  const selected = model.findings.find(finding => finding.rank === selectedRank) ?? model.findings[0];
  const evidenceCalls = useMemo(
    () => (selected ? callsForFinding(selected, model.calls) : topCalls(model.calls, 8)),
    [model.calls, selected],
  );
  const evidenceProfile = useMemo(() => summarizeEvidence(evidenceCalls), [evidenceCalls]);
  const evidenceBasis = useMemo(() => findingEvidenceBasis(selected, model.calls), [model.calls, selected]);
  const evidenceColumns = useMemo<Array<ColumnDef<CallRow>>>(
    () => [...callColumns.slice(0, 8), callActionColumn({ onOpenInvestigator, onCopyCallLink, labelPrefix: 'workbench call' })],
    [onCopyCallLink, onOpenInvestigator],
  );

  function selectFinding(finding: Finding) {
    setSelectedRank(finding.rank);
    syncSelectedFindingUrl(finding.rank);
    setEvidenceStatus(`Selected ${finding.title}`);
  }

  function inspectCalls(finding: Finding) {
    const calls = callsForFinding(finding, model.calls);
    setEvidenceStatus(`Evidence table focused on ${finding.title}: ${calls.length} aggregate rows`);
  }

  return (
    <div className="workbench-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Investigator Workbench</h1>
          <p>Ranked findings, evidence, and aggregate-only drilldowns.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label="Stored Snapshot" tone="blue" />
          <StatusBadge label="Live API" tone="green" />
        </div>
      </div>

      <Panel title="What Is Driving Usage?" subtitle="Ranked by estimated credit impact">
        <div className="finding-list">
          {model.findings.map(finding => (
            <FindingCard
              key={finding.rank}
              finding={finding}
              active={finding.rank === selected?.rank}
              onSelect={() => selectFinding(finding)}
            />
          ))}
        </div>
      </Panel>

      <div className="stacked-panels">
        <Panel title="Usage Drain Over Time" subtitle="Observed credits vs baseline">
          <LineChart series={model.actualVsPredictedSeries} yLabel="Credits" height={230} />
        </Panel>
        <Panel title="Projected Weekly Credits" subtitle="Plan trend with confidence intervals">
          <LineChart series={model.weeklyCreditSeries} yLabel="Credits" height={230} />
        </Panel>
        <Panel title="Cache Ratio Over Time" subtitle="Cache behavior around usage windows">
          <LineChart
            series={model.cacheSeries}
            yLabel="Cache Hit %"
            height={220}
            valueFormatter={value => `${value}%`}
          />
        </Panel>
        <Panel
          title="Evidence Table"
          subtitle={evidenceStatus || `${formatNumber(evidenceCalls.length)} preview calls - ${evidenceBasis.summary}`}
          action={<StatusBadge label="Rows open investigator" tone="green" />}
        >
          <DataTable
            columns={evidenceColumns}
            data={evidenceCalls}
            compact
            emptyLabel="No loaded aggregate calls match this finding."
getRowId={call => call.id}
getRowActionLabel={call => callInvestigatorRowLabel(call, 'workbench call')}
onRowActivate={call => onOpenInvestigator(call.id)}
            ariaLabel="Investigator evidence calls"
          />
        </Panel>
      </div>

      {selected ? (
        <SelectedFinding
          finding={selected}
          calls={evidenceCalls}
            evidenceBasis={evidenceBasis}
            evidenceProfile={evidenceProfile}
            onInspectCalls={() => inspectCalls(selected)}
            onCopyCallLink={onCopyCallLink}
            onOpenInvestigator={onOpenInvestigator}
          />
      ) : null}
    </div>
  );
}

function FindingCard({
  finding,
  active,
  onSelect,
}: {
  finding: Finding;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <article className={active ? 'finding-card active' : 'finding-card'}>
      <div className="finding-rank">{finding.rank}</div>
      <div className="finding-body">
        <h3>{finding.title}</h3>
        <p>{finding.summary}</p>
        <div className="finding-stats">
          <strong>{formatNumber(finding.credits)}</strong>
          <span>{finding.share.toFixed(1)}% total</span>
        </div>
      </div>
      <StatusBadge label={finding.severity} tone={finding.severity === 'High' ? 'red' : 'orange'} />
      <button className="inline-button" type="button" onClick={onSelect}>
        Inspect <ArrowRight size={14} />
      </button>
    </article>
  );
}

function SelectedFinding({
  finding,
  calls,
  evidenceBasis,
  evidenceProfile,
  onInspectCalls,
  onCopyCallLink,
  onOpenInvestigator,
}: {
  finding: Finding;
  calls: CallRow[];
  evidenceBasis: EvidenceBasis;
  evidenceProfile: EvidenceProfile;
  onInspectCalls: () => void;
  onCopyCallLink: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
}) {
  return (
    <aside className="side-panel">
      <Panel title="Selected Finding" subtitle={finding.title}>
        <div className="detail-stat-grid">
          <span>
            <strong>{formatNumber(finding.credits)}</strong>
            Est. Credits
          </span>
          <span>
            <strong>{finding.share.toFixed(1)}%</strong>
            Share
          </span>
          <span>
            <strong>2.4x</strong>
            vs baseline
          </span>
        </div>

        <h3>Why This Matters</h3>
        <p>{finding.summary} The signal is visible in aggregate timing, token, cache, and cost measures.</p>

        <div className="finding-module">
          <div className="section-heading compact">
            <h3>Evidence Profile</h3>
            <span>{calls.length ? `${calls.length} matched` : 'No matches'}</span>
          </div>
          <div className="evidence-list">
            <span>
              Calls <strong>{formatNumber(evidenceProfile.callCount)}</strong>
            </span>
            <span>
              Tokens <strong>{formatCompact(evidenceProfile.totalTokens)}</strong>
            </span>
            <span>
              Cache hit <strong>{pct(evidenceProfile.avgCachePct)}</strong>
            </span>
            <span>
              Cost <strong>{money(evidenceProfile.estimatedCost)}</strong>
            </span>
            <span>
              Models <strong>{formatNumber(evidenceProfile.modelCount)}</strong>
            </span>
          </div>
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
          <h3>Evidence Calls</h3>
            <span>{calls.length ? 'Open any row' : 'No loaded rows'}</span>
          </div>
          {calls.length ? (
            <ol className="thread-mini-timeline">
              {calls.slice(0, 4).map(call => (
              <li
                key={`${finding.rank}-${call.id}`}
                className="workbench-call-row has-row-action"
                tabIndex={0}
                aria-label={`Open investigator for workbench evidence call ${call.thread} ${call.model}`}
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
                    {call.model} / {call.effort} - {formatCompact(call.totalTokens)} tokens - {pct(call.cachedPct)} cache
                  </em>
                  <div className="thread-call-actions table-action-group">
                    <button
                      className="table-action-button"
                      type="button"
                      aria-label={`Open investigator for workbench evidence call ${call.thread} ${call.model}`}
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
                      aria-label={`Copy link for workbench evidence call ${call.thread} ${call.model}`}
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
            <p className="empty-state">No loaded aggregate calls match this finding.</p>
          )}
        </div>

        <div className="finding-module">
          <h3>Suggested Next Step</h3>
          <ul className="compact-list">
            <li>{recommendationForFinding(finding)}</li>
          </ul>
        </div>

        <button className="primary-button stretch" type="button" onClick={onInspectCalls}>
          Inspect Calls <ArrowRight size={16} />
        </button>
      </Panel>
    </aside>
  );
}

function callsForFinding(finding: Finding, calls: CallRow[]): CallRow[] {
  const title = finding.title.toLowerCase();
  const rows = [...calls];

  if (title.includes('cache')) {
    return rows
      .filter(call => call.signal === 'cache-risk' || call.cachedPct < 35 || call.uncachedInput > 50_000)
      .sort(
        (left, right) =>
          left.cachedPct - right.cachedPct ||
          right.uncachedInput - left.uncachedInput ||
          right.totalTokens - left.totalTokens,
      )
      .slice(0, 8);
  }

  if (title.includes('effort') || title.includes('reasoning')) {
    return rows
      .filter(call => call.effort.toLowerCase() === 'high' || call.reasoningOutput > 0)
      .sort((left, right) => right.reasoningOutput - left.reasoningOutput || right.totalTokens - left.totalTokens)
      .slice(0, 8);
  }

  if (title.includes('tool') || title.includes('output')) {
    return rows
      .filter(call => call.tags.some(tag => ['file-heavy', 'subagent', 'large'].includes(tag)) || call.output > 25_000)
      .sort((left, right) => right.output - left.output || right.input - left.input)
      .slice(0, 8);
  }

  const threadHint = threadHintFromFinding(title);
  if (threadHint) {
    const matches = rows.filter(call => call.thread.toLowerCase().includes(threadHint));
    if (matches.length) {
      return topCalls(matches, 8);
    }
  }

  if (title.includes('thread')) {
    return topCalls(rows, 8);
  }

  return rows.sort((left, right) => right.credits - left.credits || right.totalTokens - left.totalTokens).slice(0, 8);
}

function findingFromUrl(findings: Finding[]): Finding | undefined {
  const rank = Number(new URLSearchParams(window.location.search).get('finding') ?? '');
  return Number.isFinite(rank) ? findings.find(finding => finding.rank === rank) : undefined;
}

function syncSelectedFindingUrl(rank: number) {
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'investigator');
  url.searchParams.set('finding', String(rank));
  window.history.replaceState(null, '', url);
}

function findingEvidenceBasis(finding: Finding | undefined, calls: CallRow[]): EvidenceBasis {
  const title = finding?.title.toLowerCase() ?? '';
  if (title.includes('cache')) {
    return {
      selection: 'cache-risk, cache below 35%, or uncached input above 50K',
      ordering: 'lowest cache hit rate, then highest uncached input',
      limit: 'top 8 loaded aggregate rows',
      summary: 'cache-risk evidence sorted by weakest cache',
    };
  }
  if (title.includes('effort') || title.includes('reasoning')) {
    return {
      selection: 'high-effort calls or calls with reasoning output',
      ordering: 'reasoning output descending, then total tokens',
      limit: 'top 8 loaded aggregate rows',
      summary: 'effort evidence sorted by reasoning output',
    };
  }
  if (title.includes('tool') || title.includes('output')) {
    return {
      selection: 'file-heavy, subagent, large-tag, or high-output calls',
      ordering: 'output tokens descending, then input tokens',
      limit: 'top 8 loaded aggregate rows',
      summary: 'tool/output evidence sorted by output tokens',
    };
  }
  const threadHint = threadHintFromFinding(title);
  if (threadHint && calls.some(call => call.thread.toLowerCase().includes(threadHint))) {
    return {
      selection: 'calls matching the thread named in this finding',
      ordering: 'total tokens descending, then estimated cost',
      limit: 'top 8 loaded aggregate rows',
      summary: 'thread-matched evidence sorted by total tokens',
    };
  }
  return {
    selection: title.includes('thread') ? 'highest-impact calls across loaded threads' : 'highest estimated Codex credit impact',
    ordering: title.includes('thread') ? 'total tokens descending, then estimated cost' : 'Codex credits descending, then total tokens',
    limit: 'top 8 loaded aggregate rows',
    summary: title.includes('thread') ? 'thread evidence sorted by total tokens' : 'credit-impact evidence sorted by credits',
  };
}

function topCalls(calls: CallRow[], limit: number): CallRow[] {
  return [...calls].sort((left, right) => right.totalTokens - left.totalTokens || right.cost - left.cost).slice(0, limit);
}

function threadHintFromFinding(title: string): string {
  const threadMatch = title.match(/thread:\s*([a-z0-9._-]+)/i);
  return threadMatch?.[1]?.toLowerCase() ?? '';
}

function summarizeEvidence(calls: CallRow[]): EvidenceProfile {
  const callCount = calls.length;
  const totalTokens = calls.reduce((sum, call) => sum + call.totalTokens, 0);
  const estimatedCost = calls.reduce((sum, call) => sum + call.cost, 0);
  const avgCachePct = callCount ? calls.reduce((sum, call) => sum + call.cachedPct, 0) / callCount : 0;
  const modelCount = new Set(calls.map(call => call.model)).size;
  return { callCount, totalTokens, avgCachePct, estimatedCost, modelCount };
}

function recommendationForFinding(finding: Finding): string {
  const title = finding.title.toLowerCase();
  if (title.includes('cache')) return 'Open the lowest-cache evidence call and inspect uncached input before continuing.';
  if (title.includes('effort') || title.includes('reasoning')) {
    return 'Open a high-effort call and verify the effort level matched the task complexity.';
  }
  if (title.includes('tool') || title.includes('output')) {
    return 'Open a tool-heavy call and trim noisy command output before the next model turn.';
  }
  return 'Open the highest-impact call and inspect thread context before deciding whether to split or summarize.';
}
