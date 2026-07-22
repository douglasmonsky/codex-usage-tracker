import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, FlaskConical, RefreshCw } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import {
  observeCompressionAnalysis,
  runCompressionAnalysis,
  type CompressionApiPayload,
  type CompressionProfile,
} from '../../api/compressionLab';
import type { ContextRuntime } from '../../api/types';
import { FeatureMaturityBanner } from '../../components/FeatureMaturityBanner';
import { compressionProfileQueryOptions } from '../../data/compressionQueries';
import { Button, MetricReadout, ProgressBar, StatusBadge, Surface } from '../../design';
import { formatCompact, formatNumber } from '../shared/format';
import styles from './CompressionLabPage.module.css';

type CompressionLabPageProps = {
  contextRuntime: ContextRuntime;
  includeArchived: boolean;
  since: string | null;
  sourceKey: string;
  sourceRevision: string;
};

export function CompressionLabPage({
  contextRuntime,
  includeArchived,
  since,
  sourceKey,
  sourceRevision,
}: CompressionLabPageProps) {
  const queryClient = useQueryClient();
  const canUseLive = !contextRuntime.fileMode && Boolean(contextRuntime.apiToken);
  const request = {
    runtime: contextRuntime,
    includeArchived,
    since,
    sourceKey,
    sourceRevision,
  };
  const profileOptions = compressionProfileQueryOptions(request);
  const profileQuery = useQuery({ ...profileOptions, enabled: canUseLive });
  const runControllerRef = useRef<AbortController | null>(null);
  const [running, setRunning] = useState(false);
  const [runProgress, setRunProgress] = useState<CompressionApiPayload | null>(null);
  const [runError, setRunError] = useState<string | null>(null);
  const payload = profileQuery.data;
  const profile = payload?.profile;
  const missing = payload?.error?.code === 'compression_run_not_found';
  const incompleteRunId = payload?.error?.code === 'compression_run_not_complete'
    ? payload.run_id
    : null;

  useEffect(() => () => {
    runControllerRef.current?.abort();
    runControllerRef.current = null;
  }, []);

  useEffect(() => {
    if (!canUseLive || !incompleteRunId || !payload) return undefined;
    const controller = new AbortController();
    runControllerRef.current?.abort();
    runControllerRef.current = controller;
    setRunning(true);
    setRunError(null);
    setRunProgress(payload);
    void observeCompressionAnalysis(
      contextRuntime,
      { includeArchived, since },
      payload,
      {
        signal: controller.signal,
        onProgress: setRunProgress,
      },
    ).then(completed => {
      queryClient.setQueryData(profileOptions.queryKey, completed);
    }).catch(error => {
      if (!controller.signal.aborted) setRunError(errorMessage(error));
    }).finally(() => {
      if (runControllerRef.current === controller) {
        runControllerRef.current = null;
        if (!controller.signal.aborted) setRunning(false);
      }
    });
    return () => {
      controller.abort();
      if (runControllerRef.current === controller) runControllerRef.current = null;
    };
  }, [
    canUseLive,
    contextRuntime.apiToken,
    contextRuntime.fileMode,
    includeArchived,
    incompleteRunId,
    queryClient,
    since,
    sourceKey,
    sourceRevision,
  ]);

  async function analyze(refresh: boolean) {
    const controller = new AbortController();
    runControllerRef.current?.abort();
    runControllerRef.current = controller;
    setRunning(true);
    setRunError(null);
    setRunProgress(null);
    try {
      const completed = await runCompressionAnalysis(contextRuntime, request, {
        refresh,
        signal: controller.signal,
        onProgress: setRunProgress,
      });
      queryClient.setQueryData(profileOptions.queryKey, completed);
    } catch (error) {
      if (!controller.signal.aborted) setRunError(errorMessage(error));
    } finally {
      if (runControllerRef.current === controller) {
        runControllerRef.current = null;
        if (!controller.signal.aborted) setRunning(false);
      }
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Context efficiency research</p>
          <h1>Compression Lab</h1>
          <p>Measure repeated context and tool-output exposure, allocate overlap once, and rank the largest local savings opportunities.</p>
        </div>
        <div className={styles.headerActions}>
          <StatusBadge tone={profile ? 'positive' : 'neutral'}>
            {profile ? cacheLabel(payload, profile) : 'No current profile'}
          </StatusBadge>
          <Button
            variant="primary"
            disabled={!canUseLive || running || profileQuery.isPending}
            onClick={() => void analyze(Boolean(profile))}
          >
            {profile ? <RefreshCw aria-hidden="true" /> : <FlaskConical aria-hidden="true" />}
            {running ? 'Analyzing' : profile ? 'Refresh analysis' : 'Analyze usage'}
          </Button>
        </div>
      </header>

      <FeatureMaturityBanner
        kind="transitioning"
        title="Available during transition"
        description="This workspace remains available in Release N while its future placement is prepared."
        replacement={{
          operation: 'usage_analyze(goal="token_waste"); full-profile compression tools through 0.24.x',
          href: '?view=explore&mode=calls',
        }}
      />

      {running && runProgress?.progress ? (
        <Surface tone="subtle" className={styles.progressPanel} aria-live="polite">
          <ProgressBar
            label="Compression analysis progress"
            value={runProgress.progress.percent}
          />
          <div className={styles.progressMeta}>
            <strong>{detectorLabel(runProgress.progress.current_detector)}</strong>
            <span>
              {runProgress.progress.completed_detectors} of {runProgress.progress.total_detectors} detectors
              {' / '}{formatNumber(runProgress.progress.records_examined)} records examined
            </span>
          </div>
        </Surface>
      ) : null}

      {running && runProgress?.error?.code === 'compression_database_busy' ? (
        <Surface tone="subtle" className={styles.loadingState} role="status">
          Waiting for the usage refresh to finish before starting analysis...
        </Surface>
      ) : null}

      {profileQuery.isPending && canUseLive ? (
        <Surface tone="subtle" className={styles.loadingState} role="status">Loading the newest exact-scope profile...</Surface>
      ) : null}

      {runError ? <div className={styles.error} role="alert">Compression analysis failed: {runError}</div> : null}
      {profileQuery.error ? <div className={styles.error} role="alert">Profile unavailable: {errorMessage(profileQuery.error)}</div> : null}

      {!canUseLive ? (
        <EmptyState title="Local server required" detail="Compression Lab jobs run against the local SQLite index and are unavailable in static-file mode." />
      ) : missing && !running ? (
        <EmptyState title="No analysis for this scope yet" detail="Start one persistent run. Returning to this scope will reuse the completed profile until its source revision changes." />
      ) : profile ? (
        <ProfileWorkspace payload={payload} profile={profile} />
      ) : null}
    </div>
  );
}

function ProfileWorkspace({
  payload,
  profile,
}: {
  payload: CompressionApiPayload;
  profile: CompressionProfile;
}) {
  const observed = numberValue(profile.observed_exposure?.total);
  const estimate = profile.portfolio_estimate ?? {};
  const low = numberValue(estimate.low);
  const likely = numberValue(estimate.likely);
  const high = numberValue(estimate.high);
  const families = [...(profile.families ?? [])].sort(
    (left, right) => numberValue(right.adjusted_estimate?.likely) - numberValue(left.adjusted_estimate?.likely),
  );
  const coverage = profile.coverage ?? payload.coverage ?? {};
  const caveats = profile.caveats ?? payload.caveats ?? [];
  const warnings = profile.warnings ?? payload.warnings ?? [];

  return (
    <>
      <section className={styles.answerBand} aria-labelledby="compression-answer-title">
        <div>
          <span>Overlap-adjusted portfolio</span>
          <h2 id="compression-answer-title">{formatCompact(likely)} tokens are the current likely savings estimate</h2>
          <p>{formatCompact(low)} to {formatCompact(high)} across {formatNumber(numberValue(profile.candidate_count))} ranked candidates. Exposure is measured; avoidability remains an estimate.</p>
        </div>
        <StatusBadge tone={warnings.length ? 'caution' : 'positive'}>
          {warnings.length ? `${warnings.length} coverage warnings` : 'Profile complete'}
        </StatusBadge>
      </section>

      <div className={styles.metricGrid}>
        <Surface><MetricReadout label="Observed exposure" value={formatCompact(observed)} detail="Tokens in analyzed components" /></Surface>
        <Surface><MetricReadout label="Likely avoidable" value={formatCompact(likely)} detail="Overlap-adjusted estimate" /></Surface>
        <Surface><MetricReadout label="Estimate range" value={`${formatCompact(low)} to ${formatCompact(high)}`} detail="Low to high heuristic" /></Surface>
        <Surface><MetricReadout label="Candidates" value={formatNumber(numberValue(profile.candidate_count))} detail={`${families.length} detector families`} /></Surface>
      </div>

      <div className={styles.analysisGrid}>
        <Surface className={styles.familyPanel}>
          <div className={styles.panelHeader}>
            <div><h2>Opportunity families</h2><p>Largest overlap-adjusted detector portfolios first.</p></div>
            <StatusBadge tone="context">Shared MCP profile</StatusBadge>
          </div>
          <div className={styles.tableWrap}>
            <table aria-label="Compression opportunity families">
              <thead><tr><th>Family</th><th>Candidates</th><th>Likely savings</th><th>Range</th></tr></thead>
              <tbody>
                {families.map((row, index) => (
                  <tr key={`${row.family ?? 'unclassified'}-${index}`}>
                    <td><strong>{titleCase(row.family ?? 'unclassified')}</strong></td>
                    <td className={styles.numeric}>{formatNumber(numberValue(row.candidate_count))}</td>
                    <td className={styles.numeric}>{formatCompact(numberValue(row.adjusted_estimate?.likely))}</td>
                    <td className={styles.numeric}>{formatCompact(numberValue(row.adjusted_estimate?.low))} to {formatCompact(numberValue(row.adjusted_estimate?.high))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Surface>

        <Surface tone="subtle" className={styles.methodPanel}>
          <div className={styles.panelHeader}>
            <div><h2>Profile integrity</h2><p>Scope, coverage, and disclosure state for this result.</p></div>
            <FlaskConical aria-hidden="true" />
          </div>
          <dl className={styles.methodList}>
            <div><dt>Cache</dt><dd>{cacheLabel(payload, profile)}</dd></div>
            <div><dt>Calls covered</dt><dd>{formatNumber(numberValue(coverage.call_count))}</dd></div>
            <div><dt>Content mode</dt><dd>{titleCase(profile.content_mode ?? 'aggregate')}</dd></div>
            <div><dt>Raw fragments</dt><dd>{profile.includes_raw_fragments ? 'Included' : 'Not included'}</dd></div>
            <div><dt>Build time</dt><dd>{formatDuration(numberValue(profile.duration_ms))}</dd></div>
          </dl>
          {warnings.length ? (
            <div className={styles.warning} role="alert">
              <AlertTriangle aria-hidden="true" />
              <span>{warnings.map(warning => String(warning.message ?? warning.code ?? 'Coverage warning')).join('; ')}</span>
            </div>
          ) : null}
        </Surface>
      </div>

      <Surface tone="subtle" className={styles.caveats}>
        <h2>Interpretation limits</h2>
        <ul>{caveats.map(caveat => <li key={caveat}>{caveat}</li>)}</ul>
      </Surface>
    </>
  );
}

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <Surface tone="subtle" className={styles.emptyState}>
      <FlaskConical aria-hidden="true" />
      <div><h2>{title}</h2><p>{detail}</p></div>
    </Surface>
  );
}

function cacheLabel(payload: CompressionApiPayload, profile: CompressionProfile): string {
  const mode = profile.cache?.mode ?? payload.cache?.mode;
  if (mode === 'exact') return 'Exact warm profile';
  if (mode === 'incremental') return 'Incremental profile';
  if (payload.cache?.reused || profile.cache?.reused) return 'Reused profile';
  return 'Fresh profile';
}

function detectorLabel(value: string | null): string {
  return value ? `${titleCase(value)} detector` : 'Preparing detector pipeline';
}

function titleCase(value: string): string {
  return value.replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
}

function numberValue(value: unknown): number {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric : 0;
}

function formatDuration(milliseconds: number): string {
  return milliseconds < 1_000 ? `${formatNumber(milliseconds)} ms` : `${(milliseconds / 1_000).toFixed(1)} s`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
