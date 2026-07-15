import { useQuery } from '@tanstack/react-query';
import { Download, FlaskConical, RefreshCw, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  loadAllowanceEvidenceExport,
  type AllowanceWindowKind,
} from '../../api/allowance';
import {
  loadAllowanceAnalysis,
  loadAllowanceAnalysisJob,
  loadAllowanceEvidence,
  loadAllowanceSeries,
  loadAllowanceStatus,
  startAllowanceAnalysis,
  type AllowanceSeriesRequest,
} from '../../api/allowanceIntelligence';
import type { AllowanceAnalysisPayload, ContextRuntime, DashboardModel } from '../../api/types';
import { Button, MetricReadout, PageLoadProgress, SegmentedControl, StatusBadge, Surface } from '../../design';
import { Visualization } from '../../visualization';
import { csvDateStamp } from '../shared/exportCsv';
import { AllowanceEvidenceLedger } from './AllowanceEvidenceLedger';
import { AllowanceIntelligenceEvidenceTable } from './AllowanceIntelligenceEvidenceTable';
import { buildAllowanceReadout, type AllowanceReadout } from './allowanceIntelligenceModel';
import { buildAllowanceIntelligenceVisualization } from './allowanceIntelligenceVisualization';
import {
  allowanceEvidenceCallsForCurrentUrl,
  buildAllowanceWorkspace,
  buildFallbackAllowanceExport,
  evaluateAllowanceHypothesis,
  type AllowanceHypothesis,
  type AllowanceTone,
} from './allowanceModel';
import { buildAllowanceVisualizationSpec } from './allowanceVisualization';
import { allowanceAnalysisPollInterval, allowanceStatusPollInterval, isPageVisible } from './allowancePolling';
import styles from './LimitsPage.module.css';

type LimitsPageProps = {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  includeArchived?: boolean;
  sourceRevision?: string;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

export { allowanceEvidenceCallsForCurrentUrl };

type RangePreset = NonNullable<AllowanceSeriesRequest['rangePreset']>;
type Granularity = NonNullable<AllowanceSeriesRequest['granularity']>;

export function LimitsPage(props: LimitsPageProps) {
  const canUseLive = Boolean(props.contextRuntime.apiToken) && !props.contextRuntime.fileMode;
  return canUseLive ? <LiveLimitsPage {...props} /> : <StaticLimitsPage {...props} />;
}

function LiveLimitsPage({
  contextRuntime,
  includeArchived = false,
  onOpenInvestigator,
  onCopyCallLink,
}: LimitsPageProps) {
  const initialState = readLimitState();
  const [windowKind, setWindowKind] = useState<AllowanceWindowKind>(initialState.windowKind);
  const [rangePreset, setRangePreset] = useState<RangePreset>('8w');
  const [granularity, setGranularity] = useState<Granularity>('auto');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [evidenceCursors, setEvidenceCursors] = useState<(string | undefined)[]>([undefined]);
  const [analysisJobId, setAnalysisJobId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState('Canonical allowance evidence ready');
  const [exporting, setExporting] = useState(false);
  const queryScope = [contextRuntime.apiToken, includeArchived] as const;
  const customStartAt = dateBoundary(customStart, false);
  const customEndAt = dateBoundary(customEnd, true);
  const customReady = rangePreset !== 'custom' || Boolean(customStartAt && customEndAt);
  const evidenceBefore = evidenceCursors.at(-1);

  const statusQuery = useQuery({
    queryKey: ['allowance-v2', 'status', ...queryScope],
    queryFn: ({ signal }) => loadAllowanceStatus(contextRuntime, { includeArchived }, signal),
    staleTime: 0,
    refetchInterval: query => allowanceStatusPollInterval(
      query.state.data?.data_state,
      query.state.fetchFailureCount,
      isPageVisible(),
    ),
    refetchIntervalInBackground: false,
    retry: false,
  });
  const allowanceRevision = statusQuery.data?.revision ?? '';
  const seriesQuery = useQuery({
    queryKey: ['allowance-v2', 'series', ...queryScope, allowanceRevision, windowKind, rangePreset, granularity, customStartAt, customEndAt],
    queryFn: ({ signal }) => loadAllowanceSeries(contextRuntime, {
      includeArchived,
      rangePreset,
      granularity,
      windowKind,
      startAt: customStartAt,
      endAt: customEndAt,
    }, signal),
    enabled: Boolean(allowanceRevision) && customReady,
    staleTime: Number.POSITIVE_INFINITY,
    placeholderData: previous => previous,
    retry: false,
  });
  const evidenceQuery = useQuery({
    queryKey: ['allowance-v2', 'evidence', ...queryScope, allowanceRevision, windowKind, evidenceBefore, 100, 'local'],
    queryFn: ({ signal }) => loadAllowanceEvidence(contextRuntime, {
      includeArchived,
      before: evidenceBefore,
      limit: 100,
      order: 'desc',
      privacyMode: 'local',
      windowKind,
    }, signal),
    enabled: Boolean(allowanceRevision),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const analysisQuery = useQuery({
    queryKey: ['allowance-v2', 'analysis', ...queryScope, allowanceRevision, 'weekly'],
    queryFn: ({ signal }) => loadAllowanceAnalysis(contextRuntime, { includeArchived }, signal),
    enabled: Boolean(allowanceRevision),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const analysisJobQuery = useQuery({
    queryKey: ['allowance-v2', 'analysis-job', contextRuntime.apiToken, analysisJobId],
    queryFn: ({ signal }) => loadAllowanceAnalysisJob(contextRuntime, analysisJobId ?? '', signal),
    enabled: Boolean(analysisJobId),
    refetchInterval: query => allowanceAnalysisPollInterval(query.state.data?.status, isPageVisible()),
    refetchIntervalInBackground: false,
    retry: false,
  });
  const refetchAnalysis = analysisQuery.refetch;
  useEffect(() => {
    setEvidenceCursors([undefined]);
  }, [allowanceRevision, windowKind]);
  useEffect(() => {
    if (analysisJobQuery.data?.status === 'completed') {
      setAnalysisJobId(null);
      setStatusMessage('Allowance analysis completed');
      void refetchAnalysis();
    } else if (analysisJobQuery.data?.status === 'failed') {
      setAnalysisJobId(null);
      setStatusMessage('Allowance analysis failed');
    }
  }, [analysisJobQuery.data?.status, refetchAnalysis]);

  const readout = useMemo(() => buildAllowanceReadout(statusQuery.data), [statusQuery.data]);
  const chartSpec = useMemo(() => seriesQuery.data
    ? buildAllowanceIntelligenceVisualization(seriesQuery.data, statusQuery.data, windowKind)
    : null, [seriesQuery.data, statusQuery.data, windowKind]);
  const loading = statusQuery.isFetching || seriesQuery.isFetching || evidenceQuery.isFetching || analysisQuery.isFetching;
  const error = statusQuery.error ?? seriesQuery.error ?? evidenceQuery.error ?? analysisQuery.error;
  const completedModules = Number(Boolean(statusQuery.data)) + Number(Boolean(seriesQuery.data))
    + Number(Boolean(evidenceQuery.data)) + Number(Boolean(analysisQuery.data));

  function selectWindow(next: AllowanceWindowKind) {
    setWindowKind(next);
    syncIntelligenceUrl(next, rangePreset, granularity);
    setStatusMessage(next === 'weekly' ? 'Weekly primary window selected' : '5-hour rolling context selected');
  }

  function selectRange(next: RangePreset) {
    setRangePreset(next);
    syncIntelligenceUrl(windowKind, next, granularity);
  }

  function selectGranularity(next: Granularity) {
    setGranularity(next);
    syncIntelligenceUrl(windowKind, rangePreset, next);
  }

  async function refreshStatus() {
    if (loading) return;
    setStatusMessage('Checking for new allowance evidence…');
    const result = await statusQuery.refetch();
    setStatusMessage(result.isError ? 'Allowance status check failed' : 'Allowance status checked');
  }

  async function exportEvidence() {
    if (exporting) return;
    setExporting(true);
    try {
      const payload = await loadAllowanceEvidenceExport(contextRuntime, { includeArchived, limit: null });
      downloadJson(`codex-allowance-evidence-${csvDateStamp()}.json`, payload);
      setStatusMessage('Strict allowance evidence exported');
    } catch (exportError) {
      setStatusMessage(`Export failed: ${errorMessage(exportError)}`);
    } finally {
      setExporting(false);
    }
  }

  async function runAnalysis() {
    if (analysisJobId) return;
    setStatusMessage('Starting selection-corrected allowance analysis…');
    try {
      const job = await startAllowanceAnalysis(contextRuntime, { includeArchived });
      setAnalysisJobId(job.job_id);
      setStatusMessage('Allowance analysis running');
    } catch (analysisError) {
      setStatusMessage(`Analysis failed: ${errorMessage(analysisError)}`);
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Allowance intelligence</p>
          <h1>Limits</h1>
          <p>Observed allowance snapshots first, personal estimates second, with uncertainty and provenance kept visible.</p>
        </div>
        <div className={styles.headerActions}>
          <Button onClick={exportEvidence} disabled={exporting}><Download />{exporting ? 'Exporting' : 'Export evidence'}</Button>
          <Button variant="primary" onClick={refreshStatus} disabled={loading}><RefreshCw />{loading ? 'Updating' : 'Check for new data'}</Button>
        </div>
      </header>

      <PageLoadProgress active={loading} completed={completedModules} total={4} label="Loading allowance intelligence" error={error ? errorMessage(error) : null} updating={completedModules > 0} />

      <div className={styles.statusRow} role="status" aria-live="polite">
        <StatusBadge tone={freshnessTone(statusQuery.data?.data_state)}>{freshnessLabel(statusQuery.data?.data_state)}</StatusBadge>
        <StatusBadge tone="positive">Canonical usage</StatusBadge>
        <StatusBadge tone="neutral">{statusQuery.data?.quality.copied_rows_excluded ?? 0} copied excluded</StatusBadge>
        <span>{error ? `Live allowance data unavailable: ${errorMessage(error)}` : statusMessage}</span>
      </div>

      <section className={styles.answerBand} data-tone={readout.primary.kind === 'estimated' ? 'context' : 'positive'} aria-labelledby="limits-answer-title">
        <div className={styles.answerCopy}>
          <span>{readout.primary.label}</span>
          <h2 id="limits-answer-title">{readout.primary.value}</h2>
          <p>{readout.primary.detail}</p>
        </div>
        <div className={styles.answerMeta}>
          <StatusBadge tone={readout.primary.kind === 'observed' ? 'positive' : 'context'}>{readout.primary.grade}</StatusBadge>
          <span>{statusQuery.data?.data_as_of ? `Data as of ${shortDateTime(statusQuery.data.data_as_of)}` : 'Awaiting a local observation'}</span>
        </div>
      </section>

      <div className={styles.metricGrid}>
        <ReadoutSurface readout={readout.weekly} />
        <ReadoutSurface readout={readout.fiveHour} />
        <ReadoutSurface readout={readout.reset} />
        <ReadoutSurface readout={readout.capacity} />
      </div>

      <Surface className={styles.trendPanel}>
        <div className={styles.modeBar}>
          <div><p className={styles.eyebrow}>History explorer</p><h2>Usage percentage over time</h2><p>Zoom from day-level snapshots to multi-month cycles. Reset markers break the observed sequence.</p></div>
          <SegmentedControl label="Allowance window" options={[{ label: 'Weekly', value: 'weekly' }, { label: '5-hour', value: 'five_hour' }]} value={windowKind} onValueChange={selectWindow} />
        </div>
        <div className={styles.rangeControls}>
          <SegmentedControl
            label="History range"
            options={[{ label: '24h', value: '24h' }, { label: '7d', value: '7d' }, { label: '8w', value: '8w' }, { label: '6m', value: '6m' }, { label: 'Custom', value: 'custom' }]}
            value={rangePreset}
            onValueChange={selectRange}
          />
          <label className={styles.controlField}>Granularity
            <select value={granularity} onChange={event => selectGranularity(event.target.value as Granularity)}>
              <option value="auto">Automatic</option><option value="raw">Every snapshot</option><option value="hour">Hourly</option>
              <option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option><option value="cycle">By reset cycle</option>
            </select>
          </label>
        </div>
        {rangePreset === 'custom' ? (
          <div className={styles.customRange}>
            <label>Start date<input type="date" value={customStart} onChange={event => setCustomStart(event.target.value)} /></label>
            <label>End date<input type="date" value={customEnd} onChange={event => setCustomEnd(event.target.value)} /></label>
            {!customReady ? <span>Choose both dates to load the custom range.</span> : null}
          </div>
        ) : null}
        {chartSpec ? <Visualization spec={chartSpec} height={380} /> : <div className={styles.chartPlaceholder}>{seriesQuery.isFetching ? 'Loading observed history…' : 'No observed history for this range.'}</div>}
      </Surface>

      <div className={styles.insightGrid}>
        <InsightCard title="Validated estimate" readout={readout.forecast} />
        <InsightCard title="Conditional pace" readout={readout.pace} />
        <AnalysisCard analysis={analysisQuery.data} running={Boolean(analysisJobId)} onRun={runAnalysis} />
      </div>

      <AllowanceIntelligenceEvidenceTable
        rows={evidenceQuery.data?.rows ?? []}
        page={evidenceCursors.length}
        hasOlder={Boolean(evidenceQuery.data?.next_cursor)}
        loading={evidenceQuery.isFetching}
        onNewer={() => setEvidenceCursors(current => current.length > 1 ? current.slice(0, -1) : current)}
        onOlder={() => evidenceQuery.data?.next_cursor && setEvidenceCursors(current => [...current, evidenceQuery.data?.next_cursor ?? undefined])}
        onOpenCall={onOpenInvestigator}
        onCopyCallLink={onCopyCallLink}
      />

      <details className={styles.caveats}>
        <summary><ShieldCheck />Method, confidence, and boundaries</summary>
        <ul>
          <li>Observed percentages are local Codex rate-limit snapshots. They are not reconstructed from token totals.</li>
          <li>Personal calibration uses completed, quality-approved cycles with strict priced-usage coverage and one vote per cycle.</li>
          <li>Forecasts appear only after time-ordered holdout validation; otherwise the dashboard stays observed-only.</li>
          <li>Change claims use a selection-corrected cycle-block permutation test and exclude low-quality cycles.</li>
          <li>The tracker cannot read OpenAI's internal allowance or billing ledger.</li>
        </ul>
      </details>
    </div>
  );
}

function StaticLimitsPage({
  model,
  contextRuntime,
  includeArchived = false,
  sourceRevision = '',
  onOpenInvestigator,
  onCopyCallLink,
}: LimitsPageProps) {
  const initialState = readLimitState();
  const [windowKind, setWindowKind] = useState<AllowanceWindowKind>(initialState.windowKind);
  const [hypothesis, setHypothesis] = useState<AllowanceHypothesis>(initialState.hypothesis);
  const [evaluatedHypothesis, setEvaluatedHypothesis] = useState<AllowanceHypothesis | null>(null);
  const [analysisJobId, setAnalysisJobId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState('Stored allowance evidence ready');
  const [exporting, setExporting] = useState(false);
  const canUseLive = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const queryScope = [contextRuntime.apiToken, includeArchived] as const;
  const statusQuery = useQuery({
    queryKey: ['allowance-v2', 'status', ...queryScope],
    queryFn: ({ signal }) => loadAllowanceStatus(contextRuntime, { includeArchived }, signal),
    enabled: canUseLive,
    staleTime: 0,
    refetchInterval: query => allowanceStatusPollInterval(
      query.state.data?.data_state,
      query.state.fetchFailureCount,
      isPageVisible(),
    ),
    refetchIntervalInBackground: false,
    retry: false,
  });
  const allowanceRevision = statusQuery.data?.revision ?? '';
  const seriesQuery = useQuery({
    queryKey: ['allowance-v2', 'series', ...queryScope, allowanceRevision, windowKind, '8w', 'auto'],
    queryFn: ({ signal }) => loadAllowanceSeries(contextRuntime, {
      includeArchived,
      rangePreset: '8w',
      granularity: 'auto',
      windowKind,
    }, signal),
    enabled: canUseLive && Boolean(allowanceRevision),
    staleTime: Number.POSITIVE_INFINITY,
    placeholderData: previous => previous,
    retry: false,
  });
  const evidenceQuery = useQuery({
    queryKey: ['allowance-v2', 'evidence', ...queryScope, allowanceRevision, windowKind, 100, 'local'],
    queryFn: ({ signal }) => loadAllowanceEvidence(contextRuntime, {
      includeArchived,
      limit: 100,
      order: 'desc',
      privacyMode: 'local',
      windowKind,
    }, signal),
    enabled: canUseLive && Boolean(allowanceRevision),
    staleTime: Number.POSITIVE_INFINITY,
    placeholderData: previous => previous,
    retry: false,
  });
  const analysisQuery = useQuery({
    queryKey: ['allowance-v2', 'analysis', ...queryScope, allowanceRevision, 'weekly'],
    queryFn: ({ signal }) => loadAllowanceAnalysis(contextRuntime, { includeArchived }, signal),
    enabled: canUseLive && Boolean(allowanceRevision),
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
  const analysisJobQuery = useQuery({
    queryKey: ['allowance-v2', 'analysis-job', contextRuntime.apiToken, analysisJobId],
    queryFn: ({ signal }) => loadAllowanceAnalysisJob(contextRuntime, analysisJobId ?? '', signal),
    enabled: canUseLive && Boolean(analysisJobId),
    refetchInterval: query => allowanceAnalysisPollInterval(query.state.data?.status, isPageVisible()),
    refetchIntervalInBackground: false,
    retry: false,
  });
  useEffect(() => {
    if (analysisJobQuery.data?.status === 'completed') {
      setAnalysisJobId(null);
      setStatusMessage('Allowance analysis completed');
      void analysisQuery.refetch();
    } else if (analysisJobQuery.data?.status === 'failed') {
      setAnalysisJobId(null);
      setStatusMessage('Allowance analysis failed');
    }
  }, [analysisJobQuery.data?.status, analysisQuery]);
  const workspace = useMemo(
    () => buildAllowanceWorkspace(model, undefined, undefined, allowanceRevision || sourceRevision),
    [allowanceRevision, model, sourceRevision],
  );
  const selectedWindow = windowKind === 'weekly' ? workspace.weekly : workspace.fiveHour;
  const chartSpec = useMemo(
    () => buildAllowanceVisualizationSpec(workspace, windowKind),
    [windowKind, workspace],
  );
  const hypothesisResult = evaluatedHypothesis
    ? evaluateAllowanceHypothesis(workspace, evaluatedHypothesis)
    : null;
  const answerTitle = analysisQuery.data?.status === 'no_supported_change'
    ? 'No weekly regime change detected'
    : workspace.answer.title;
  const loading = statusQuery.isFetching || seriesQuery.isFetching || evidenceQuery.isFetching || analysisQuery.isFetching;
  const error = statusQuery.error ?? seriesQuery.error ?? evidenceQuery.error ?? analysisQuery.error;
  const completedModules = Number(Boolean(statusQuery.data))
    + Number(Boolean(seriesQuery.data))
    + Number(Boolean(evidenceQuery.data))
    + Number(Boolean(analysisQuery.data));

  function selectWindow(next: AllowanceWindowKind) {
    setWindowKind(next);
    syncLimitUrl(next, hypothesis);
    setStatusMessage(next === 'weekly' ? 'Weekly primary signal selected' : '5-hour noisy context selected');
  }

  function selectHypothesis(next: AllowanceHypothesis) {
    setHypothesis(next);
    setEvaluatedHypothesis(null);
    syncLimitUrl(windowKind, next);
  }

  async function refreshEvidence() {
    if (!canUseLive || loading) return;
    setStatusMessage('Checking allowance status...');
    const result = await statusQuery.refetch();
    setStatusMessage(result.isError ? 'Allowance status check failed' : 'Allowance status checked');
  }

  async function exportEvidence() {
    if (exporting) return;
    setExporting(true);
    try {
      const payload = canUseLive
        ? await loadAllowanceEvidenceExport(contextRuntime, { includeArchived, limit: null })
        : buildFallbackAllowanceExport(workspace);
      downloadJson(`codex-allowance-evidence-${csvDateStamp()}.json`, payload);
      setStatusMessage('Strict allowance evidence exported');
    } catch (exportError) {
      setStatusMessage(`Export failed: ${errorMessage(exportError)}`);
    } finally {
      setExporting(false);
    }
  }

  async function testHypothesis() {
    setEvaluatedHypothesis(hypothesis);
    if (canUseLive && analysisQuery.data?.status === 'missing') {
      setStatusMessage('Starting allowance analysis...');
      try {
        const job = await startAllowanceAnalysis(contextRuntime, { includeArchived });
        setAnalysisJobId(job.job_id);
        setStatusMessage('Allowance analysis running');
      } catch (analysisError) {
        setStatusMessage(`Analysis failed: ${errorMessage(analysisError)}`);
      }
      return;
    }
    setStatusMessage('Weekly hypothesis evaluated against stored analysis');
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Allowance intelligence</p>
          <h1>Limits</h1>
          <p>Weekly evidence first, rolling-window context second, and no claim beyond the loaded local data.</p>
        </div>
        <div className={styles.headerActions}>
          <Button onClick={exportEvidence} disabled={exporting}><Download />{exporting ? 'Exporting' : 'Export evidence'}</Button>
          <Button variant="primary" onClick={refreshEvidence} disabled={!canUseLive || loading}>
            <RefreshCw />{loading ? 'Refreshing' : 'Refresh evidence'}
          </Button>
        </div>
      </header>

      <PageLoadProgress
        active={canUseLive && loading}
        completed={completedModules}
        total={4}
        label="Loading allowance intelligence"
        error={canUseLive && error ? errorMessage(error) : null}
        updating={completedModules > 0}
      />

      <div className={styles.statusRow} role="status" aria-live="polite">
        <StatusBadge tone={statusQuery.data ? 'positive' : 'neutral'}>{statusQuery.data ? 'Canonical live status' : 'Loaded aggregate fallback'}</StatusBadge>
        {statusQuery.data ? (
          <StatusBadge tone="neutral">{statusQuery.data.quality.copied_rows_excluded} copied excluded</StatusBadge>
        ) : null}
        <StatusBadge tone={workspace.readiness.ready_for_public_claim ? 'positive' : 'caution'}>
          {workspace.readiness.ready_for_public_claim ? 'Local claim threshold met' : 'Research caution'}
        </StatusBadge>
        <span>{error ? `Live detector unavailable: ${errorMessage(error)}` : statusMessage}</span>
      </div>

      <section className={styles.answerBand} data-tone={workspace.answer.tone} aria-labelledby="limits-answer-title">
        <div className={styles.answerCopy}>
          <span>{workspace.answer.label}</span>
          <h2 id="limits-answer-title">{answerTitle}</h2>
          <p>{workspace.answer.detail}</p>
        </div>
        <div className={styles.answerMeta}>
          <StatusBadge tone={workspace.answer.tone}>{workspace.answer.badge}</StatusBadge>
          <span>{workspace.weekly.positiveSpanCount} weekly spans · {workspace.readiness.detector_version}</span>
        </div>
      </section>

      <div className={styles.metricGrid}>
        <Surface><MetricReadout label="Observed snapshots" value={workspace.weekly.observationCount.toLocaleString()} detail="Weekly primary signal" /></Surface>
        <Surface><MetricReadout label="Positive spans" value={workspace.weekly.positiveSpanCount.toLocaleString()} detail={`${workspace.weekly.resetCount} resets / rollbacks`} /></Surface>
        <Surface><MetricReadout label="Candidate ratio" value={capacityRatio(workspace.candidate?.capacity_ratio)} detail="Recent vs earlier proxy" /></Surface>
        <Surface><MetricReadout label="Unexplained movement" value={unexplainedMovement(workspace.candidate?.unexplained_usage_percent)} detail={workspace.candidate?.outside_usage_possible ? 'Outside usage possible' : 'No large outside-usage flag'} /></Surface>
      </div>

      <div className={styles.modeBar}>
        <div>
          <h2>{windowKind === 'weekly' ? 'Weekly allowance evidence' : '5-hour rolling context'}</h2>
          <p>{windowKind === 'weekly' ? 'Primary change detector with recent evidence shown first.' : 'Secondary context only; rolling-window movement is noisy.'}</p>
        </div>
        <SegmentedControl
          label="Allowance window"
          options={[{ label: 'Weekly', value: 'weekly' }, { label: '5-hour', value: 'five_hour' }]}
          value={windowKind}
          onValueChange={selectWindow}
        />
      </div>

      <Visualization spec={chartSpec} height={340} />

      <div className={styles.analysisGrid}>
        <Surface className={styles.hypothesisPanel}>
          <div className={styles.panelHeader}>
            <div><h2>Hypothesis check</h2><p>Evaluate a community-style claim using the server detector result.</p></div>
            <FlaskConical aria-hidden="true" />
          </div>
          <SegmentedControl
            label="Allowance hypothesis"
            options={[
              { label: 'Allowance decreased', value: 'decreased' },
              { label: 'Behavior stayed stable', value: 'stable' },
            ]}
            value={hypothesis}
            onValueChange={selectHypothesis}
          />
          <div className={styles.hypothesisResult} data-tone={hypothesisResult?.tone ?? 'neutral'}>
            {hypothesisResult ? (
              <>
                <StatusBadge tone={hypothesisResult.tone}>{hypothesisResult.badge}</StatusBadge>
                <strong>{hypothesisResult.title}</strong>
                <p>{hypothesisResult.detail}</p>
              </>
            ) : (
              <>
                <StatusBadge tone="neutral">Not evaluated</StatusBadge>
                <strong>Choose a claim, then test it against the weekly detector</strong>
                <p>The dashboard reports the backend evidence grade; it does not run a separate client-side detector.</p>
              </>
            )}
          </div>
          <Button variant="primary" onClick={testHypothesis}><FlaskConical />Test weekly claim</Button>
        </Surface>

        <Surface tone="subtle" className={styles.methodPanel}>
          <div className={styles.panelHeader}>
            <div><h2>Evidence grade</h2><p>What supports or weakens the current result.</p></div>
            <StatusBadge tone={gradeTone(workspace.primaryGrade)}>{gradeLabel(workspace.primaryGrade)}</StatusBadge>
          </div>
          <dl className={styles.methodList}>
            <div><dt>Method</dt><dd>{workspace.candidate?.statistical_evidence.method ?? 'No candidate split tested'}</dd></div>
            <div><dt>Effect size</dt><dd>{statistic(workspace.candidate?.statistical_evidence.effect_size_cliffs_delta)}</dd></div>
            <div><dt>One-sided p-value</dt><dd>{statistic(workspace.candidate?.statistical_evidence.p_value_one_sided)}</dd></div>
            <div><dt>95% median intervals</dt><dd>{intervalStatus(workspace)}</dd></div>
          </dl>
        </Surface>
      </div>

      <AllowanceEvidenceLedger
        window={selectedWindow}
        onOpenCall={onOpenInvestigator}
        onCopyCallLink={onCopyCallLink}
      />

      <details className={styles.caveats}>
        <summary><ShieldCheck />Method, readiness, and caveats</summary>
        <ul>
          {workspace.readiness.reasons.map(reason => <li key={reason}>{reason}</li>)}
          {workspace.notes.map(note => <li key={note}>{note}</li>)}
          <li>Weekly observations are the primary signal. The 5-hour counter is rolling-window context.</li>
          <li>This project cannot read OpenAI's internal allowance ledger.</li>
        </ul>
      </details>
    </div>
  );
}

function ReadoutSurface({ readout }: { readout: AllowanceReadout['weekly'] }) {
  return (
    <Surface className={styles.readoutCard}>
      <MetricReadout label={readout.label} value={readout.value} detail={readout.detail} />
      <StatusBadge tone={readoutTone(readout.kind)}>{readout.grade}</StatusBadge>
    </Surface>
  );
}

function InsightCard({ title, readout }: { title: string; readout: AllowanceReadout['forecast'] }) {
  return (
    <Surface className={styles.insightCard}>
      <div className={styles.panelHeader}><div><p className={styles.eyebrow}>Personal model</p><h2>{title}</h2></div><StatusBadge tone={readoutTone(readout.kind)}>{readout.grade}</StatusBadge></div>
      <strong className={styles.insightValue}>{readout.value}</strong>
      <p>{readout.detail}</p>
    </Surface>
  );
}

function AnalysisCard({
  analysis,
  running,
  onRun,
}: {
  analysis: AllowanceAnalysisPayload | undefined;
  running: boolean;
  onRun: () => void;
}) {
  const status = analysis?.status ?? 'missing';
  const effect = analysis?.effect_size;
  return (
    <Surface className={styles.insightCard}>
      <div className={styles.panelHeader}>
        <div><p className={styles.eyebrow}>Capacity change</p><h2>{analysisTitle(status)}</h2></div>
        <StatusBadge tone={analysisTone(status)}>{status.replaceAll('_', ' ')}</StatusBadge>
      </div>
      <dl className={styles.methodList}>
        <div><dt>Eligible cycles</dt><dd>{analysis?.eligible_cycle_count ?? 0}</dd></div>
        <div><dt>Adjusted p-value</dt><dd>{formatStatistic(analysis?.adjusted_p_value)}</dd></div>
        <div><dt>Median before</dt><dd>{formatCredits(effect?.median_before_credits_per_percent)}</dd></div>
        <div><dt>Median after</dt><dd>{formatCredits(effect?.median_after_credits_per_percent)}</dd></div>
      </dl>
      <p>{analysisExplanation(analysis)}</p>
      <Button variant="primary" onClick={onRun} disabled={running}>{running ? 'Analysis running' : status === 'missing' ? 'Run analysis' : 'Re-run for current revision'}</Button>
    </Surface>
  );
}

function readoutTone(kind: AllowanceReadout['weekly']['kind']): 'positive' | 'context' | 'neutral' {
  return kind === 'observed' ? 'positive' : kind === 'estimated' ? 'context' : 'neutral';
}

function freshnessTone(state: string | undefined): 'positive' | 'caution' | 'neutral' {
  return state === 'fresh' ? 'positive' : state === 'aging' || state === 'partial' ? 'caution' : 'neutral';
}

function freshnessLabel(state: string | undefined): string {
  if (!state) return 'Awaiting status';
  return state === 'partial' ? 'Partial evidence' : `${state[0].toUpperCase()}${state.slice(1)} data`;
}

function analysisTone(status: AllowanceAnalysisPayload['status']): 'positive' | 'caution' | 'neutral' {
  return status === 'supported_change' ? 'caution' : status === 'no_supported_change' ? 'positive' : 'neutral';
}

function analysisTitle(status: AllowanceAnalysisPayload['status']): string {
  if (status === 'supported_change') return 'Supported capacity shift';
  if (status === 'no_supported_change') return 'No supported capacity shift';
  if (status === 'insufficient_evidence') return 'More completed cycles needed';
  return 'Analysis not computed';
}

function analysisExplanation(analysis: AllowanceAnalysisPayload | undefined): string {
  if (!analysis || analysis.status === 'missing') return 'Run the aggregate-only detector for this semantic data revision.';
  if (analysis.status === 'insufficient_evidence') return 'The detector withheld a claim because too few quality-approved completed cycles exist on both sides of a candidate boundary.';
  if (analysis.status === 'supported_change') return 'The best candidate boundary cleared both the selection-adjusted significance and strong-effect gates.';
  return 'No candidate boundary cleared the selection-adjusted significance and strong-effect gates.';
}

function formatStatistic(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value < 0.001 ? '<0.001' : value.toFixed(3);
}

function formatCredits(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)} / 1%`;
}

function dateBoundary(value: string, end: boolean): string | undefined {
  if (!value) return undefined;
  const timestamp = Date.parse(`${value}T${end ? '23:59:59.999' : '00:00:00.000'}Z`);
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : undefined;
}

function shortDateTime(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(timestamp);
}

function syncIntelligenceUrl(windowKind: AllowanceWindowKind, range: RangePreset, granularity: Granularity) {
  if (typeof window === 'undefined') return;
  const url = new URL(window.location.href);
  url.searchParams.set('limit_window', windowKind);
  url.searchParams.set('limit_range', range);
  url.searchParams.set('limit_granularity', granularity);
  window.history.replaceState({}, '', `${url.pathname}?${url.searchParams.toString()}${url.hash}`);
}

function readLimitState(): { windowKind: AllowanceWindowKind; hypothesis: AllowanceHypothesis } {
  const params = new URLSearchParams(window.location.search);
  return {
    windowKind: params.get('limit_window') === 'five_hour' ? 'five_hour' : 'weekly',
    hypothesis: params.get('limit_hypothesis') === 'stable' ? 'stable' : 'decreased',
  };
}

function syncLimitUrl(windowKind: AllowanceWindowKind, hypothesis: AllowanceHypothesis) {
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'usage-drain');
  if (windowKind === 'weekly') url.searchParams.delete('limit_window');
  else url.searchParams.set('limit_window', windowKind);
  if (hypothesis === 'decreased') url.searchParams.delete('limit_hypothesis');
  else url.searchParams.set('limit_hypothesis', hypothesis);
  window.history.replaceState(null, '', url);
}

function capacityRatio(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`;
}

function unexplainedMovement(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 10) / 10}%`;
}

function statistic(value: number | null | undefined): string {
  return value === null || value === undefined ? 'Not available' : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function intervalStatus(workspace: ReturnType<typeof buildAllowanceWorkspace>): string {
  const evidence = workspace.candidate?.statistical_evidence;
  const before = evidence?.median_confidence_interval_before_95;
  const after = evidence?.median_confidence_interval_after_95;
  if (before?.available && after?.available) return 'Available for both regimes';
  if (before?.available || after?.available) return 'Available for one regime; the other sample is too small';
  return 'Unavailable at the current sample size';
}

function gradeTone(grade: string): AllowanceTone {
  if (grade === 'strong_local_evidence') return 'risk';
  if (grade === 'possible_regime_change' || grade === 'inconclusive_other_usage_possible') return 'caution';
  if (grade === 'no_change_detected') return 'positive';
  if (grade === 'counter_noise_likely') return 'context';
  return 'neutral';
}

function gradeLabel(grade: string): string {
  return grade.replaceAll('_', ' ');
}

function downloadJson(filename: string, payload: unknown): void {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
