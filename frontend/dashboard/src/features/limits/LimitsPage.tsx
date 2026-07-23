import { useQuery } from '@tanstack/react-query';
import { Download, FlaskConical, RefreshCw, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

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
} from '../../api/allowanceIntelligence';
import type { ContextRuntime, DashboardModel } from '../../api/types';
import { Button, MetricReadout, PageLoadProgress, SegmentedControl, StatusBadge, Surface } from '../../design';
import { Visualization } from '../../visualization';
import { csvDateStamp } from '../shared/exportCsv';
import { AllowanceCapacityChangeTimeline } from './AllowanceCapacityChangeTimeline';
import { AllowanceCapacityLegend } from './AllowanceCapacityLegend';
import { AllowanceCapacityMethodology } from './AllowanceCapacityMethodology';
import { AllowanceCapacityStatusRow } from './AllowanceCapacityStatusRow';
import { AllowanceEvidenceLedger } from './AllowanceEvidenceLedger';
import { AllowanceHistoryControls, type Granularity, type RangePreset } from './AllowanceHistoryControls';
import { AllowanceIntelligenceEvidenceTable } from './AllowanceIntelligenceEvidenceTable';
import {
  capacityRatio,
  gradeLabel,
  gradeTone,
  intervalStatus,
  statistic,
  unexplainedMovement,
} from './allowanceDisplay';
import { buildAllowanceReadout } from './allowanceIntelligenceModel';
import { buildAllowanceIntelligenceVisualization } from './allowanceIntelligenceVisualization';
import {
  allowanceEvidenceCallsForCurrentUrl,
  buildAllowanceWorkspace,
  buildFallbackAllowanceExport,
  evaluateAllowanceHypothesis,
  type AllowanceHypothesis,
} from './allowanceModel';
import { buildAllowanceVisualizationSpec } from './allowanceVisualization';
import { allowanceAnalysisPollInterval, allowanceStatusPollInterval, isPageVisible } from './allowancePolling';
import { downloadJson, errorMessage } from './limitsPageActions';
import { useAllowanceStatusEstimation, useFastAllowanceStatus } from './useAllowanceStatusEstimation';
import baseStyles from './LimitsPage.module.css';
import intelligenceStyles from './LimitsIntelligence.module.css';

const styles = { ...baseStyles, ...intelligenceStyles };

type LimitsPageProps = {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  includeArchived?: boolean;
  sourceRevision?: string;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

export { allowanceEvidenceCallsForCurrentUrl };

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
  const windowKind: AllowanceWindowKind = 'weekly';
  const [rangePreset, setRangePreset] = useState<RangePreset>('8w');
  const [granularity, setGranularity] = useState<Granularity>('cycle');
  const [showFullRange, setShowFullRange] = useState(false);
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [evidenceCursors, setEvidenceCursors] = useState<(string | undefined)[]>([undefined]);
  const [showPhysicalProvenance, setShowPhysicalProvenance] = useState(false);
  const [analysisJobId, setAnalysisJobId] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState('Canonical allowance evidence ready');
  const [exporting, setExporting] = useState(false);
  const automaticAnalysisRevisionRef = useRef<string | null>(null);
  const queryScope = [contextRuntime.apiToken, includeArchived] as const;
  const customStartAt = dateBoundary(customStart, false);
  const customEndAt = dateBoundary(customEnd, true);
  const customReady = rangePreset !== 'custom' || Boolean(customStartAt && customEndAt);
  const evidenceBefore = evidenceCursors.at(-1);

  const statusQuery = useFastAllowanceStatus(contextRuntime, includeArchived, queryScope);
  const allowanceRevision = statusQuery.data?.revision ?? ''; const allowanceStatus = useAllowanceStatusEstimation(contextRuntime, includeArchived, queryScope, statusQuery.data);
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
    queryKey: ['allowance-v2', 'evidence', ...queryScope, allowanceRevision, windowKind, evidenceBefore, 50, showPhysicalProvenance],
    queryFn: ({ signal }) => loadAllowanceEvidence(contextRuntime, {
      includeArchived,
      before: evidenceBefore,
      limit: 50,
      order: 'desc',
      privacyMode: showPhysicalProvenance ? 'local' : 'normal',
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
  useEffect(() => {
    if (!allowanceRevision
      || analysisQuery.isFetching
      || analysisQuery.data?.status !== 'missing'
      || analysisJobId
      || automaticAnalysisRevisionRef.current === allowanceRevision) return;
    automaticAnalysisRevisionRef.current = allowanceRevision;
    setStatusMessage('Starting capacity analysis for new allowance data…');
    void startAllowanceAnalysis(contextRuntime, { includeArchived })
      .then(job => {
        setAnalysisJobId(job.job_id);
        setStatusMessage('Capacity analysis running');
      })
      .catch(analysisError => {
        automaticAnalysisRevisionRef.current = null;
        setStatusMessage(`Analysis failed: ${errorMessage(analysisError)}`);
      });
  }, [allowanceRevision, analysisJobId, analysisQuery.data?.status, analysisQuery.isFetching, contextRuntime, includeArchived]);

  const readout = useMemo(() => buildAllowanceReadout(allowanceStatus), [allowanceStatus]);
  const chartSpec = useMemo(() => seriesQuery.data
    ? buildAllowanceIntelligenceVisualization(seriesQuery.data, allowanceStatus, windowKind, { showFullRange })
    : null, [seriesQuery.data, allowanceStatus, windowKind, showFullRange]);
  const rangeHasNoOlderData = Boolean(seriesQuery.data && (
    rangePreset === 'all'
    || (rangePreset === '6m'
      && seriesQuery.data.available_range.start_at
      && seriesQuery.data.requested_range.start_at
      && Date.parse(seriesQuery.data.available_range.start_at) > Date.parse(seriesQuery.data.requested_range.start_at))
  ));
  const loading = statusQuery.isFetching || seriesQuery.isFetching || evidenceQuery.isFetching || analysisQuery.isFetching;
  const error = statusQuery.error ?? seriesQuery.error ?? evidenceQuery.error ?? analysisQuery.error;
  const completedModules = Number(Boolean(statusQuery.data)) + Number(Boolean(seriesQuery.data))
    + Number(Boolean(evidenceQuery.data)) + Number(Boolean(analysisQuery.data));

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
    automaticAnalysisRevisionRef.current = null;
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

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Allowance intelligence</p>
          <h1>Limits</h1>
          <p>Track how many priced local credits correspond to each weekly allowance percentage point, with supported changes and provenance kept visible.</p>
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

      <AllowanceCapacityStatusRow readout={readout} />

      <Surface className={styles.trendPanel}>
        <div className={styles.modeBar}>
          <div><p className={styles.eyebrow}>Capacity history</p><p>Each point is one quality-approved completed reset window. The line and band summarize recent capacity without letting extreme values flatten the chart.</p></div>
          {(seriesQuery.data?.capacity_history.clipped_point_count ?? 0) > 0 ? (
            <Button onClick={() => setShowFullRange(current => !current)}>
              {showFullRange ? 'Use robust range' : 'Show full range'}
            </Button>
          ) : null}
        </div>
        <AllowanceHistoryControls
          customEnd={customEnd}
          customReady={customReady}
          customStart={customStart}
          granularity={granularity}
          rangePreset={rangePreset}
          onCustomEndChange={setCustomEnd}
          onCustomStartChange={setCustomStart}
          onGranularityChange={selectGranularity}
          onRangeChange={selectRange}
        />
        {seriesQuery.data ? (
          <p className={styles.rangeFeedback} role="status" aria-label="History range result" data-localization-attributes="aria-label">
            <strong>{rangePreset === 'all' ? 'All history' : rangePreset} selected</strong>
            {' · '}{seriesQuery.data.capacity_history.eligible_cycle_count} eligible reset windows loaded.
            {rangeHasNoOlderData ? ' No older capacity history is available.' : ''}
          </p>
        ) : null}
        {seriesQuery.data ? <AllowanceCapacityLegend series={seriesQuery.data} /> : null}
        {chartSpec ? <Visualization spec={chartSpec} height={380} /> : <div className={styles.chartPlaceholder}>{seriesQuery.isFetching ? 'Loading capacity history…' : 'No completed-cycle capacity history for this range.'}</div>}
        {seriesQuery.data ? (
          <AllowanceCapacityMethodology
            series={seriesQuery.data}
            analysis={analysisQuery.data}
          />
        ) : null}
      </Surface>

      <AllowanceCapacityChangeTimeline
        analysis={analysisQuery.data}
        evidenceRows={evidenceQuery.data?.rows ?? []}
        running={Boolean(analysisJobId)}
      />

      <AllowanceIntelligenceEvidenceTable
        analysisId={analysisQuery.data?.snapshot_id ?? null}
        rows={evidenceQuery.data?.rows ?? []}
        page={evidenceCursors.length}
        hasOlder={Boolean(evidenceQuery.data?.next_cursor)}
        loading={evidenceQuery.isFetching}
        showPhysicalProvenance={showPhysicalProvenance}
        onTogglePhysicalProvenance={show => {
          setEvidenceCursors([undefined]);
          setShowPhysicalProvenance(show);
        }}
        onNewer={() => setEvidenceCursors(current => current.length > 1 ? current.slice(0, -1) : current)}
        onOlder={() => evidenceQuery.data?.next_cursor && setEvidenceCursors(current => [...current, evidenceQuery.data?.next_cursor ?? undefined])}
        onOpenCall={onOpenInvestigator}
        onCopyCallLink={onCopyCallLink}
      />

      <details className={styles.caveats}>
        <summary><ShieldCheck />Method, confidence, and boundaries</summary>
        <ul>
          <li>Observed percentages are local Codex rate-limit snapshots. They are not reconstructed from token totals.</li>
          <li>Personal calibration uses completed, quality-approved reset windows with strict priced-usage coverage and one vote per reset identity.</li>
          <li>The weekly percentage forecast remains available through the API only when it beats time-ordered baselines; this page does not treat a failed forecast as missing capacity data.</li>
          <li>Change claims use a hierarchical cycle-block permutation test, control family-wise false positives, require a strong effect, and exclude low-quality reset windows.</li>
          <li>Five-hour allowance status is shown as observed context only because expiry makes it a rolling window; weekly monotonic capacity math is not applied to it.</li>
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

      <details className={styles.advancedControls}>
        <summary>Advanced compatibility controls</summary>
        <div className={styles.advancedControlsBody}>
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
        </div>
      </details>

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

function freshnessTone(state: string | undefined): 'positive' | 'caution' | 'neutral' {
  return state === 'fresh' ? 'positive' : state === 'aging' || state === 'partial' ? 'caution' : 'neutral';
}

function freshnessLabel(state: string | undefined): string {
  if (!state) return 'Awaiting status';
  return state === 'partial' ? 'Partial evidence' : `${state[0].toUpperCase()}${state.slice(1)} data`;
}

function dateBoundary(value: string, end: boolean): string | undefined {
  if (!value) return undefined;
  const timestamp = Date.parse(`${value}T${end ? '23:59:59.999' : '00:00:00.000'}Z`);
  return Number.isFinite(timestamp) ? new Date(timestamp).toISOString() : undefined;
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
