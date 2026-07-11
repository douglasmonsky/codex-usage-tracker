import { useQuery } from '@tanstack/react-query';
import { Download, RefreshCw } from 'lucide-react';
import { useMemo, useState } from 'react';

import { loadReportsPack } from '../../api/reports';
import type { CallRow, DashboardModel } from '../../api/types';
import type { LoadWindow } from '../../data/dataScope';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { Visualization } from '../../visualization';
import { csvDateStamp } from '../shared/exportCsv';
import { ReportEvidenceTable } from './ReportEvidenceTable';
import {
  reportDetails,
  reportEvidenceCalls,
  reportFromUrl,
  reportKey,
  syncReportUrl,
  type ReportView,
} from './reportModel';
import { buildReportVisualizationSpec } from './reportVisualization';
import styles from './ReportsPage.module.css';

type ReportsPageProps = {
  model: DashboardModel;
  refreshState: string;
  includeArchived: boolean;
  loadWindow: LoadWindow;
  loadLimit: number;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

export function reportCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  return reportEvidenceCalls(reportFromUrl(model.reports) ?? model.reports[0], model.calls);
}

export function ReportsPage({
  model,
  refreshState,
  includeArchived,
  loadWindow,
  loadLimit,
  onOpenInvestigator,
  onCopyCallLink,
}: ReportsPageProps) {
  const [selectedKey, setSelectedKey] = useState(() => reportKey(reportFromUrl(model.reports) ?? model.reports[0]));
  const [actionStatus, setActionStatus] = useState('');
  const canUseLive = Boolean(model.contextRuntime.apiToken) && !model.contextRuntime.fileMode;
  const reportLimit = loadWindow === 'rows' ? loadLimit : 0;
  const reportQuery = useQuery({
    queryKey: ['reports', 'pack', canUseLive, includeArchived, reportLimit],
    queryFn: () => loadReportsPack(model.contextRuntime, {
      limit: reportLimit,
      evidenceLimit: 8,
      includeArchived,
    }),
    enabled: canUseLive,
    staleTime: 5 * 60_000,
    placeholderData: previous => previous,
    retry: false,
  });
  const pack = canUseLive ? reportQuery.data : undefined;
  const reports: ReportView[] = pack?.reports.length ? pack.reports : model.reports;
  const active = reports.find(report => reportKey(report) === selectedKey) ?? reports[0];
  const evidenceCalls = useMemo(() => {
    const liveRows = active && pack ? pack.evidence[reportKey(active)] : undefined;
    return liveRows === undefined ? reportEvidenceCalls(active, model.calls) : liveRows;
  }, [active, model.calls, pack]);
  const details = reportDetails(active, evidenceCalls);
  const source = pack ? 'Live localhost report pack' : 'Loaded dashboard aggregates';
  const generated = pack?.generatedAt || (pack ? 'Server timestamp unavailable' : 'Current dashboard snapshot');
  const status = reportStatus(canUseLive, reportQuery, actionStatus, refreshState);
  const visualizationSpec = useMemo(() => buildReportVisualizationSpec(active, model, evidenceCalls, {
    generatedAt: generated,
    historyScope: includeArchived ? 'all' : 'active',
    source,
    sourceRevision: pack?.schema || 'dashboard aggregate model',
  }), [active, evidenceCalls, generated, includeArchived, model, pack?.schema, source]);

  async function refreshReport() {
    if (!canUseLive) return;
    setActionStatus('Refreshing selected report…');
    const result = await reportQuery.refetch();
    setActionStatus(result.isError
      ? `Refresh failed: ${errorMessage(result.error)}. Showing cached live report pack.`
      : 'Selected report refreshed');
  }

  function exportSelectedReport() {
    downloadJson(`codex-report-${reportKey(active)}-${csvDateStamp()}.json`, {
      schema: 'codex-usage-tracker-react-selected-report-v1',
      generated_at: pack?.generatedAt ?? null,
      source,
      report: active,
      method: details.method,
      caveat: details.caveat,
      evidence: evidenceCalls,
      raw_context_included: pack?.rawContextIncluded ?? false,
    });
    setActionStatus(`Exported ${active?.title ?? 'selected report'}`);
  }

  function selectReport(report: ReportView) {
    setSelectedKey(reportKey(report));
    setActionStatus(`${report.title} selected`);
    syncReportUrl(report);
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <h1>Reports</h1>
          <p>Focused local research snapshots with their methods, limits, and investigator-linked evidence.</p>
        </div>
        <div className={styles.actions}>
          <button className={styles.action} type="button" onClick={exportSelectedReport} disabled={!active}>
            <Download size={16} aria-hidden="true" />Export selected
          </button>
          <button
            className={styles.action}
            data-primary="true"
            type="button"
            onClick={refreshReport}
            disabled={!canUseLive || reportQuery.isFetching}
            title={canUseLive ? undefined : 'Live report refresh requires the localhost server.'}
          >
            <RefreshCw size={16} aria-hidden="true" />
            {canUseLive ? (reportQuery.isFetching ? 'Refreshing' : 'Refresh report') : 'Live refresh unavailable'}
          </button>
        </div>
      </header>

      <div className={styles.status} role="status" aria-live="polite">
        <StatusBadge label={pack ? 'Live report pack' : 'Aggregate fallback'} tone={pack ? 'green' : 'orange'} />
        <span>{status}</span>
      </div>

      <section className={styles.selected} aria-labelledby="selected-report-title">
        <div>
          <span className={styles.eyebrow}>{details.eyebrow}</span>
          <h2 id="selected-report-title">{active?.title ?? 'No report available'}</h2>
          <p>{active?.description}</p>
          <p>{details.finding}</p>
        </div>
        <div className={styles.selectedMeta}>
          <StatusBadge label={active?.status ?? 'Blocked'} tone={active?.status === 'Ready' ? 'green' : 'orange'} />
          <span>{active?.owner ?? 'No owner'} · {evidenceCalls.length} evidence rows</span>
        </div>
      </section>

      <div className={styles.switcher} role="group" aria-label="Select report">
        {reports.map(report => (
          <button
            key={reportKey(report)}
            type="button"
            aria-pressed={reportKey(report) === reportKey(active)}
            onClick={() => selectReport(report)}
          >
            {report.title}
          </button>
        ))}
      </div>

      <div className={styles.workspace}>
        <section className={styles.main} aria-label="Report evidence">
          <Visualization spec={visualizationSpec} height={320} />
          <Panel
            title="Report Evidence Calls"
            subtitle={`${evidenceCalls.length} aggregate rows · select a row to open Call Investigator`}
            action={<StatusBadge label="Investigator linked" tone="green" />}
          >
            <ReportEvidenceTable
              calls={evidenceCalls}
              onOpenInvestigator={onOpenInvestigator}
              onCopyCallLink={onCopyCallLink}
            />
          </Panel>
        </section>

        <aside className={styles.research}>
          <Panel title="Research Notes" subtitle="Interpretation boundary">
            <section><h3>Method</h3><p>{details.method}</p></section>
            <section><h3>Caveat</h3><p>{details.caveat}</p></section>
            <section><h3>Evidence privacy</h3><p>Raw context is not included here; inspect an explicitly linked call in Call Investigator.</p></section>
          </Panel>
          <Panel title="Generation Metadata" subtitle="Provenance for this view">
            <dl className={styles.metadata}>
              <div><dt>Source</dt><dd>{source}</dd></div>
              <div><dt>Generated</dt><dd>{generated}</dd></div>
              <div><dt>Schema</dt><dd>{pack?.schema || 'dashboard aggregate model'}</dd></div>
              <div><dt>Matched</dt><dd>{pack ? pack.totalMatchedRows.toLocaleString() : model.calls.length.toLocaleString()} loaded rows</dd></div>
            </dl>
          </Panel>
        </aside>
      </div>
    </div>
  );
}

function reportStatus(
  canUseLive: boolean,
  query: { isLoading: boolean; isFetching: boolean; isStale: boolean; error: unknown; data: unknown },
  actionStatus: string,
  refreshState: string,
): string {
  if (actionStatus) return actionStatus;
  if (!canUseLive) return refreshState || 'Static mode: using the loaded aggregate snapshot.';
  if (query.isLoading) return 'Loading live report pack…';
  if (query.error) return `Live report pack unavailable: ${errorMessage(query.error)}. Using loaded aggregate fallback.`;
  if (query.isFetching) return 'Refreshing live report pack…';
  if (query.data && query.isStale) return 'Cached live report pack is stale; refresh is available.';
  return 'Live report pack ready.';
}

function downloadJson(filename: string, payload: unknown): void {
  const serialized = JSON.stringify(payload, null, 2);
  const blob = new Blob([serialized], { type: 'application/json;charset=utf-8' });
  const objectUrl = typeof URL.createObjectURL === 'function'
    ? URL.createObjectURL(blob)
    : `data:application/json;charset=utf-8,${encodeURIComponent(serialized)}`;
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  if (objectUrl.startsWith('blob:') && typeof URL.revokeObjectURL === 'function') URL.revokeObjectURL(objectUrl);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
