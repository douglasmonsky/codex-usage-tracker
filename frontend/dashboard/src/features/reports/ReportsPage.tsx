import type { ColumnDef } from '@tanstack/react-table';
import { Copy, Download, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { loadReportsPack, type ReportsPackModel } from '../../api/reports';
import type { BarDatum, CallRow, DashboardModel, ReportSummary } from '../../api/types';
import { BarChart } from '../../charts/BarChart';
import { LineChart } from '../../charts/LineChart';
import { DataTable } from '../../components/DataTable';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { csvDateStamp } from '../shared/exportCsv';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import { callActionColumn, callInvestigatorRowLabel, weeklyColumns } from '../shared/tables';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';

type ReportsPageProps = {
  model: DashboardModel;
  onRefresh: () => void;
  refreshState: string;
  includeArchived: boolean;
  loadLimit: number;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

type ReportEvidenceProfile = {
  calls: number;
  credits: number;
  cost: number;
  avgCachePct: number;
  highEffort: number;
};

type ReportEvidenceBasis = {
  selection: string;
  ordering: string;
  limit: string;
  summary: string;
};

type ReportView = ReportSummary & { key?: string };

type FastModeSummary = {
  buckets: BarDatum[];
  candidateCount: number;
  bestDurationSeconds: number;
  medianDurationSeconds: number;
  lowEffortCount: number;
  fastFlagCount: number;
  totalCredits: number;
};

export function reportCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  const active = reportFromUrl(model.reports) ?? model.reports[0];
  return reportEvidenceCalls(active, model.calls);
}

export function ReportsPage({
  model,
  onRefresh,
  refreshState,
  includeArchived,
  loadLimit,
  onOpenInvestigator,
  onCopyCallLink,
}: ReportsPageProps) {
  const [activeReportId, setActiveReportId] = useState(() => reportIdFromUrl(model.reports) ?? reportKey(model.reports[0]));
  const [exportStatus, setExportStatus] = useState('');
  const [reportPack, setReportPack] = useState<ReportsPackModel | null>(null);
  const [reportPackStatus, setReportPackStatus] = useState('');
  const reports: ReportView[] = reportPack?.reports.length ? reportPack.reports : model.reports;
  const active = reports.find(report => reportKey(report) === activeReportId || report.title === activeReportId) ?? reports[0];
  const evidenceCalls = useMemo(() => {
    const liveRows = active ? reportPack?.evidence[reportKey(active)] : null;
    return liveRows?.length ? liveRows : reportEvidenceCalls(active, model.calls);
  }, [active, model.calls, reportPack]);
  const evidenceProfile = useMemo(() => summarizeReportEvidence(evidenceCalls), [evidenceCalls]);
  const evidenceBasis = useMemo(() => reportEvidenceBasis(active), [active]);
  const fastModeActive = isFastReport(active);
  const fastModeSummary = useMemo(() => summarizeFastModeEvidence(evidenceCalls), [evidenceCalls]);

  useEffect(() => {
    if (!model.contextRuntime.apiToken || model.contextRuntime.fileMode) {
      setReportPack(null);
      setReportPackStatus('');
      return undefined;
    }

    let cancelled = false;
    setReportPackStatus('Loading live report pack...');
    loadReportsPack(model.contextRuntime, {
      limit: loadLimit || model.calls.length || 500,
      evidenceLimit: 8,
      includeArchived,
    })
      .then(pack => {
        if (cancelled) return;
        setReportPack(pack);
        setReportPackStatus(
          `Live report pack: ${pack.reports.length} reports, ${pack.rowCount} evidence rows`,
        );
      })
      .catch(error => {
        if (cancelled) return;
        setReportPack(null);
        setReportPackStatus(`${errorMessage(error)}; using loaded aggregate rows`);
      });

    return () => {
      cancelled = true;
    };
  }, [includeArchived, loadLimit, model.calls.length, model.contextRuntime]);
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
      callActionColumn({ onOpenInvestigator, onCopyCallLink, labelPrefix: 'report evidence call' }),
    ],
    [onCopyCallLink, onOpenInvestigator],
  );

function refreshReport() {
  setExportStatus('');
  onRefresh();
}

function exportReportPack() {
  const payload = reportPack?.rawPayload ?? {
    schema: 'codex-usage-tracker-react-report-pack-v1',
    activeReport: active?.title ?? null,
    reports,
    weeklyWindows: model.weeklyWindows,
    activeEvidenceCalls: evidenceCalls.map(call => ({
      id: call.id,
      thread: call.thread,
      model: call.model,
      effort: call.effort,
      credits: callCredits(call),
      cost: call.cost,
      cachedPct: call.cachedPct,
    })),
    threadSummaries: model.threads.map(thread => ({
      name: thread.name,
      turns: thread.turns,
      totalTokens: thread.totalTokens,
      cost: thread.cost,
      cachePct: thread.cachePct,
      coldResumeRisk: thread.coldResumeRisk,
    })),
  };
  downloadJson(`codex-report-pack-${csvDateStamp()}.json`, payload);
  setExportStatus(`Exported ${reports.length} ${reportPack ? 'live ' : ''}report snapshots`);
}

  return (
    <div className="reports-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Reports</h1>
          <p>Research-style report snapshots generated from local aggregate data.</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button" onClick={exportReportPack}>
            <Download size={16} /> Export Pack
          </button>
          <button className="primary-button" type="button" onClick={refreshReport}>
            <RefreshCw size={16} /> Refresh Report
          </button>
        </div>
      </div>

 <Panel title="Report Library" subtitle={exportStatus || reportPackStatus || refreshState}>
        <div className="report-list">
          {reports.map(report => (
            <ReportCard
              key={report.title}
              report={report}
              active={report.title === active?.title}
              onSelect={() => selectReport(report)}
            />
          ))}
        </div>
      </Panel>

      <div className="stacked-panels">
        {fastModeActive ? (
          <Panel
            title="Fast Mode Proxy"
            subtitle={`${fastModeSummary.candidateCount.toLocaleString()} fast candidates by duration; rows below open Call Investigator`}
          >
            {fastModeSummary.candidateCount ? (
              <BarChart data={fastModeSummary.buckets} valueLabel={value => `${formatNumber(value)} calls`} />
            ) : (
              <p className="empty-state">No low-effort or fast-tagged aggregate calls in selected report evidence.</p>
            )}
          </Panel>
        ) : (
          <Panel title={active?.title ?? 'Weekly Credits'} subtitle="Projected credits with interval table">
            <LineChart series={reportChartSeries(active, model)} yLabel={reportChartLabel(active)} />
          </Panel>
        )}
        <Panel title="Cost Curves" subtitle="Cumulative estimated cost by thread">
          <BarChart data={model.threads.map(thread => ({ label: thread.name, value: thread.cost }))} valueLabel={money} />
        </Panel>
        {fastModeActive ? (
          <Panel title="Fast Candidate Breakdown" subtitle="Duration proxy, effort mix, and credit concentration">
            <div className="finding-stats">
              <span>
                <strong>{durationLabel(fastModeSummary.bestDurationSeconds)}</strong>
                fastest candidate
              </span>
              <span>
                <strong>{durationLabel(fastModeSummary.medianDurationSeconds)}</strong>
                median duration
              </span>
              <span>
                <strong>{formatNumber(fastModeSummary.lowEffortCount)}</strong>
                low-effort calls
              </span>
              <span>
                <strong>{formatNumber(fastModeSummary.fastFlagCount)}</strong>
                fast-tagged calls
              </span>
              <span>
                <strong>{formatCompact(fastModeSummary.totalCredits)}</strong>
                estimated credits
              </span>
            </div>
          </Panel>
        ) : null}
        <Panel title="Usage Drain Model" subtitle="Actual vs predicted local estimate">
          <LineChart series={model.actualVsPredictedSeries} yLabel="Credits" />
        </Panel>
        <Panel title="Confidence Intervals" subtitle="Weekly window evidence">
          <DataTable columns={weeklyColumns} data={model.weeklyWindows} compact ariaLabel="Report weekly windows" />
        </Panel>
        <Panel
          title="Report Evidence Calls"
          subtitle={`${active?.title ?? 'Report'}: ${evidenceCalls.length} aggregate rows - ${evidenceBasis.summary}`}
          action={<StatusBadge label="Rows open investigator" tone="green" />}
        >
          <DataTable
            columns={evidenceColumns}
            data={evidenceCalls}
            compact
            emptyLabel="No loaded aggregate calls match this report."
getRowId={call => call.id}
getRowActionLabel={call => callInvestigatorRowLabel(call, 'report evidence call')}
onRowActivate={call => onOpenInvestigator(call.id)}
            ariaLabel="Report evidence calls"
          />
        </Panel>
      </div>

      <ReportEvidencePanel
        active={active}
        evidenceBasis={evidenceBasis}
        evidenceCalls={evidenceCalls}
        evidenceProfile={evidenceProfile}
        onCopyCallLink={onCopyCallLink}
        onOpenInvestigator={onOpenInvestigator}
      />
    </div>
  );

  function selectReport(report: ReportView) {
    const id = reportKey(report);
    setActiveReportId(id);
    syncReportUrl(id);
  }
}

function ReportCard({ report, active, onSelect }: { report: ReportSummary; active: boolean; onSelect: () => void }) {
  const tone = report.status === 'Ready' ? 'green' : report.status === 'Planned' ? 'orange' : 'red';
  return (
    <button className={active ? 'report-card active' : 'report-card'} type="button" onClick={onSelect}>
      <div>
        <strong>{report.title}</strong>
        <p>{report.description}</p>
      </div>
      <span>{report.owner}</span>
      <StatusBadge label={report.status} tone={tone} />
    </button>
  );
}

function isFastReport(report: ReportSummary | undefined): boolean {
  return `${report?.title ?? ''} ${report?.owner ?? ''}`.toLowerCase().includes('fast');
}

function reportKey(report: ReportView | undefined): string {
  if (report?.key) return report.key;
  const title = `${report?.title ?? ''} ${report?.owner ?? ''}`.toLowerCase();
  if (title.includes('fast')) return 'fast-mode-proxy';
  if (title.includes('cost') || title.includes('thread')) return 'cost-curves';
  if (title.includes('remaining') || title.includes('allowance') || title.includes('weekly') || title.includes('drain')) {
    return 'usage-drain-model';
  }
  return title.replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'report';
}

function reportIdFromUrl(reports: ReportView[]): string | null {
  const id = new URLSearchParams(window.location.search).get('report')?.trim();
  if (!id) return null;
  return reports.some(report => reportKey(report) === id || report.title === id) ? id : null;
}

function reportFromUrl(reports: ReportView[]): ReportView | undefined {
  const id = reportIdFromUrl(reports);
  return id ? reports.find(report => reportKey(report) === id || report.title === id) : undefined;
}

function syncReportUrl(reportId: string) {
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'reports');
  url.searchParams.set('report', reportId);
  window.history.replaceState(null, '', url);
}

function ReportEvidencePanel({
  active,
  evidenceBasis,
  evidenceCalls,
  evidenceProfile,
  onCopyCallLink,
  onOpenInvestigator,
}: {
  active: ReportSummary | undefined;
  evidenceBasis: ReportEvidenceBasis;
  evidenceCalls: CallRow[];
  evidenceProfile: ReportEvidenceProfile;
  onCopyCallLink: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
}) {
  return (
    <aside className="side-panel">
      <Panel title="Report Evidence Profile" subtitle={active?.title ?? 'No report selected'}>
        <div className="evidence-list">
          <span>
            Calls <strong>{formatNumber(evidenceProfile.calls)}</strong>
          </span>
          <span>
            Credits <strong>{formatCompact(evidenceProfile.credits)}</strong>
          </span>
          <span>
            Est. cost <strong>{money(evidenceProfile.cost)}</strong>
          </span>
          <span>
            Avg cache <strong>{pct(evidenceProfile.avgCachePct)}</strong>
          </span>
          <span>
            High effort <strong>{formatNumber(evidenceProfile.highEffort)}</strong>
          </span>
        </div>

        <div className="finding-module">
          <div className="section-heading compact">
            <h3>Evidence Calls</h3>
            <span>{evidenceCalls.length ? 'Open any row' : 'No loaded rows'}</span>
          </div>
          {evidenceCalls.length ? (
            <ol className="thread-mini-timeline">
              {evidenceCalls.slice(0, 4).map(call => (
                <li
                  key={`${active?.title ?? 'report'}-${call.id}`}
                  className="thread-call-row has-row-action"
                  tabIndex={0}
                  aria-label={`Open investigator report side evidence call ${call.thread} ${call.model}`}
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
                    {call.model} / {call.effort} - {formatCompact(callCredits(call))} credits
                  </em>
                  <div className="thread-call-actions table-action-group">
                    <button
                      className="table-action-button"
                      type="button"
                      aria-label={`Open investigator for report side evidence call ${call.thread} ${call.model}`}
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
                      aria-label={`Copy link for report side evidence call ${call.thread} ${call.model}`}
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
            <p className="empty-state">No loaded aggregate calls match this selected report.</p>
          )}
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
        <h3>Report Notes</h3>
          <ul className="compact-list">
            <li>{reportNote(active)}</li>
            <li>Raw context remains gated in the full Call Investigator.</li>
          </ul>
        </div>
      </Panel>
    </aside>
  );
}

function reportEvidenceCalls(report: ReportSummary | undefined, calls: CallRow[]): CallRow[] {
  const title = `${report?.title ?? ''} ${report?.owner ?? ''}`.toLowerCase();
  const rows = [...calls];

  if (title.includes('fast')) {
    return rows
      .filter(call => call.fast || call.effort.toLowerCase() === 'low')
      .sort((left, right) => left.durationSeconds - right.durationSeconds || callCredits(right) - callCredits(left))
      .slice(0, 8);
  }

  if (title.includes('cost') || title.includes('thread')) {
    return rows.sort((left, right) => right.cost - left.cost || right.totalTokens - left.totalTokens).slice(0, 8);
  }

  if (title.includes('remaining') || title.includes('allowance') || title.includes('weekly') || title.includes('drain')) {
    return rows.sort((left, right) => callCredits(right) - callCredits(left) || right.totalTokens - left.totalTokens).slice(0, 8);
  }

  return rows.sort((left, right) => right.totalTokens - left.totalTokens || right.cost - left.cost).slice(0, 8);
}

function reportEvidenceBasis(report: ReportSummary | undefined): ReportEvidenceBasis {
  const title = `${report?.title ?? ''} ${report?.owner ?? ''}`.toLowerCase();
  if (title.includes('fast')) {
    return {
      selection: 'fast candidates or low-effort calls',
      ordering: 'shortest duration, then highest Codex credit impact',
      limit: 'top 8 loaded aggregate rows',
      summary: 'fast/low-effort candidates sorted by duration',
    };
  }
  if (title.includes('cost') || title.includes('thread')) {
    return {
      selection: 'highest estimated local aggregate cost',
      ordering: 'estimated cost descending, then total tokens',
      limit: 'top 8 loaded aggregate rows',
      summary: 'highest estimated cost evidence',
    };
  }
  if (title.includes('remaining') || title.includes('allowance') || title.includes('weekly') || title.includes('drain')) {
    return {
      selection: 'highest estimated Codex credit impact',
      ordering: 'Codex credits descending, then total tokens',
      limit: 'top 8 loaded aggregate rows',
      summary: 'highest credit-impact evidence',
    };
  }
  return {
    selection: 'largest aggregate token calls',
    ordering: 'total tokens descending, then estimated cost',
    limit: 'top 8 loaded aggregate rows',
    summary: 'largest token evidence',
  };
}

function summarizeReportEvidence(calls: CallRow[]): ReportEvidenceProfile {
  const callsCount = calls.length;
  return {
    calls: callsCount,
    credits: calls.reduce((sum, call) => sum + callCredits(call), 0),
    cost: calls.reduce((sum, call) => sum + call.cost, 0),
    avgCachePct: callsCount ? calls.reduce((sum, call) => sum + call.cachedPct, 0) / callsCount : 0,
    highEffort: calls.filter(call => call.effort.toLowerCase() === 'high').length,
  };
}

function summarizeFastModeEvidence(calls: CallRow[]): FastModeSummary {
  const candidateCount = calls.length;
  const durations = calls.map(call => call.durationSeconds).filter(value => Number.isFinite(value) && value > 0);
  const sortedDurations = [...durations].sort((left, right) => left - right);
  const buckets = [
    { label: 'Under 5s', max: 5, color: '#059669' },
    { label: '5-15s', max: 15, color: '#2563eb' },
    { label: '15-30s', max: 30, color: '#f59e0b' },
    { label: '30s+', max: Number.POSITIVE_INFINITY, color: '#dc2626' },
  ].map((bucket, index, allBuckets) => {
    const min = index === 0 ? 0 : allBuckets[index - 1].max;
    return {
      label: bucket.label,
      value: durations.filter(value => value >= min && value < bucket.max).length,
      color: bucket.color,
    };
  });
  return {
    buckets,
    candidateCount,
    bestDurationSeconds: sortedDurations[0] ?? 0,
    medianDurationSeconds: sortedDurations[Math.floor(sortedDurations.length / 2)] ?? 0,
    lowEffortCount: calls.filter(call => call.effort.toLowerCase() === 'low').length,
    fastFlagCount: calls.filter(call => call.fast).length,
    totalCredits: calls.reduce((sum, call) => sum + callCredits(call), 0),
  };
}

function reportChartSeries(report: ReportSummary | undefined, model: DashboardModel) {
  const title = report?.title.toLowerCase() ?? '';
  if (title.includes('remaining') || title.includes('allowance')) return model.usageRemainingSeries;
  if (title.includes('cost')) return model.costSeries;
  if (title.includes('drain')) return model.actualVsPredictedSeries;
  return model.weeklyCreditSeries;
}

function reportChartLabel(report: ReportSummary | undefined): string {
  const title = report?.title.toLowerCase() ?? '';
  if (title.includes('remaining') || title.includes('allowance')) return 'Percent';
  if (title.includes('cost')) return 'USD';
  return 'Credits';
}

function reportNote(report: ReportSummary | undefined): string {
  const title = report?.title.toLowerCase() ?? '';
  if (title.includes('fast')) return 'Fast mode evidence is inferred from aggregate low-effort and quick-call signals.';
  if (title.includes('cost')) return 'Cost evidence is sorted by estimated local aggregate cost.';
  if (title.includes('remaining') || title.includes('allowance')) {
    return 'Allowance evidence is approximate and should be read as local observation, not a universal limit.';
  }
  return 'Evidence calls are sorted by estimated usage-credit impact for this report.';
}

function callCredits(call: CallRow): number {
  return call.credits > 0 ? call.credits : call.cost * 25;
}

function durationLabel(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return 'n/a';
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

function downloadJson(filename: string, payload: unknown): void {
  const serialized = JSON.stringify(payload, null, 2);
  const blob = new Blob([serialized], { type: 'application/json;charset=utf-8' });
  const objectUrl =
    typeof URL.createObjectURL === 'function'
      ? URL.createObjectURL(blob)
      : `data:application/json;charset=utf-8,${encodeURIComponent(serialized)}`;
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  if (objectUrl.startsWith('blob:') && typeof URL.revokeObjectURL === 'function') {
    URL.revokeObjectURL(objectUrl);
  }
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
