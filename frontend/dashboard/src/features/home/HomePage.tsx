import { ArrowRight, Copy, RefreshCw } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';

import { loadHomeUsageMetrics } from '../../api/homeUsage';
import type {
  ConversationalReadiness,
  DashboardBootPayload,
  DashboardModel,
  HomeSummaryPayload,
} from '../../api/types';
import { historyScopeFromPayload } from '../../api/historyScope';
import {
  currentLoadWindowFromPayload,
  loadLimitFromPayload,
  type HistoryScope,
  type LoadWindow,
} from '../../data/dataScope';
import { Button, PageLoadProgress, StatusBadge } from '../../design';
import type { DashboardViewId } from '../../routes/dashboardSearch';
import { copyText } from '../shared/copyText';
import { OverviewMetrics } from '../overview/OverviewMetrics';
import { buildOverviewMetrics, type OverviewLoadedMetrics } from '../overview/overviewModel';
import { buildHomeModel } from './homeModel';
import styles from './HomePage.module.css';

export const followUpPromptHelp =
  'Copies a prompt to paste into Codex when the Codex Usage Tracker MCP or plugin is enabled.';

const suggestedPrompts = [
  {
    title: 'Find the biggest usage drivers',
    prompt: 'What drove my Codex usage this week? Compare it with the prior week, identify the largest drivers, and open the supporting evidence.',
  },
  {
    title: 'Investigate expensive calls and threads',
    prompt: 'Which calls or threads used the most tokens and credits in the last 24 hours? Explain why they were expensive and link the exact evidence.',
  },
  {
    title: 'Improve cache and context efficiency',
    prompt: 'Find calls with poor cache reuse or high context pressure. Rank the most actionable fixes and show the supporting calls.',
  },
  {
    title: 'Review model and effort choices',
    prompt: 'Which model and reasoning-effort choices cost the most in the last seven days? Separate configured prices, estimates, and unpriced usage.',
  },
  {
    title: 'Check allowance and capacity',
    prompt: 'Check my current weekly allowance, explain any supported capacity change, and tell me what I should do next.',
  },
  {
    title: 'Find workflow waste',
    prompt: 'Look for repeated workflow churn, oversized tool output, or unnecessary context. Recommend specific changes and explain how to verify them.',
  },
  {
    title: 'Review subagent usage',
    prompt: 'Where did Codex use subagents in the last seven days? Compare parent and subagent calls, estimate their token, cost, and credit impact, identify duplicated or low-value delegation, and link the supporting threads and calls.',
  },
] as const;

export function HomePage({
  model: dashboardModel,
  payload,
  summary,
  readiness,
  historyScope,
  loadWindow,
  loadLimit,
  scopeSince,
  refreshing,
  refreshProgressPercent = null,
  refreshProgressText = 'Refreshing local usage index',
  homeStatusLoading = false,
  homeStatusError = null,
  onRefresh,
  onOpenCall,
}: {
  model: DashboardModel;
  payload: DashboardBootPayload | null;
  summary?: HomeSummaryPayload;
  readiness?: ConversationalReadiness;
  historyScope: HistoryScope;
  loadWindow: LoadWindow;
  loadLimit: number;
  scopeSince: string | null;
  refreshing: boolean;
  refreshProgressPercent?: number | null;
  refreshProgressText?: string;
  homeStatusLoading?: boolean;
  homeStatusError?: string | null;
  onRefresh: () => void;
  onNavigate: (view: DashboardViewId) => void;
  onOpenCall: (recordId: string) => void;
}) {
  const home = useMemo(
    () => buildHomeModel({ payload, summary, readiness }),
    [payload, readiness, summary],
  );
  const usesStoredAllTime = historyScope === 'active' && loadWindow === 'all';
  const usesEmbeddedRecent =
    loadWindow === 'rows'
    && payload?.shell_boot !== true
    && dashboardModel.calls.length > 0
    && currentLoadWindowFromPayload(payload) === loadWindow
    && historyScopeFromPayload(payload) === historyScope
    && loadLimitFromPayload(payload) === loadLimit;
  const usesStoredMetrics = usesStoredAllTime || usesEmbeddedRecent;
  const scopedUsage = useQuery({
    queryKey: [
      'home-usage-v2',
      summary?.source_revision ?? 'unversioned',
      historyScope,
      loadWindow,
      loadLimit,
      scopeSince,
    ],
    queryFn: ({ signal }) => loadHomeUsageMetrics(
      payload,
      { historyScope, loadWindow, loadLimit, since: scopeSince },
      signal,
    ),
    enabled: !usesStoredMetrics && Boolean(payload?.api_token),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const usageMetrics = useMemo(
    () => usesStoredMetrics
      ? usesStoredAllTime
        ? homeUsageMetrics(summary) ?? buildOverviewMetrics(dashboardModel)
        : buildOverviewMetrics(dashboardModel)
      : scopedUsage.data ?? emptyScopeUsageMetrics(),
    [dashboardModel, scopedUsage.data, summary, usesStoredAllTime, usesStoredMetrics],
  );
  const [copyStatus, setCopyStatus] = useState('');
  const scopeUpdating = !usesStoredMetrics && scopedUsage.isFetching;
  const scopeUnavailable = !usesStoredMetrics && scopedUsage.isError;
  const progressActive = refreshing || homeStatusLoading || scopeUpdating;
  const progressLabel = refreshing
    ? refreshProgressText
    : homeStatusLoading
      ? 'Loading Home status'
      : 'Updating selected timeframe';
  const determinateRefresh = refreshing && refreshProgressPercent !== null;

  async function copyPrompt(prompt: string, success: string) {
    const copied = await copyText(prompt);
    setCopyStatus(copied ? success : 'Copy unavailable in this browser');
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Usage pulse</p>
          <h1>Overview</h1>
          <p>The important changes first, with direct paths into supporting evidence.</p>
        </div>
        <div className={styles.headerActions}>
          <StatusBadge tone={refreshing || scopeUpdating || scopeUnavailable ? 'caution' : 'neutral'}>
            {refreshing
              ? 'Refreshing'
              : scopeUpdating
                ? 'Updating timeframe'
                : scopeUnavailable
                  ? 'Timeframe unavailable'
                  : usesStoredMetrics
                    ? 'Stored snapshot'
                    : 'Selected timeframe'}
          </StatusBadge>
          <Button variant="primary" onClick={onRefresh} disabled={refreshing}>
            <RefreshCw size={16} /> {refreshing ? 'Refreshing...' : 'Refresh data'}
          </Button>
        </div>
      </header>

      <PageLoadProgress
        active={progressActive}
        completed={determinateRefresh ? refreshProgressPercent : undefined}
        total={determinateRefresh ? 100 : undefined}
        label={progressLabel}
        error={progressActive ? null : homeStatusError}
        updating={Boolean(summary)}
      />

      <OverviewMetrics
        metrics={usageMetrics}
        loadedCalls={dashboardModel.calls.length}
        availableCalls={usageMetrics.calls}
      />

      <section className={`${styles.section} ${styles.promptLibrary}`} aria-label="Codex prompt library">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>MCP-first analysis</p>
            <h2>Ask Codex about your usage</h2>
          </div>
          <StatusBadge tone={homeStatusLoading ? 'neutral' : readiness?.state === 'ready' ? 'positive' : 'caution'}>
            {homeStatusLoading
              ? 'Checking MCP'
              : readiness?.state === 'ready'
                ? 'MCP ready'
                : 'Setup may be required'}
          </StatusBadge>
        </div>
        <p className={styles.promptIntro}>
          These prompts use the Codex Usage Tracker MCP or plugin to run deterministic local
          analysis and link back to supporting evidence.
        </p>
        <details className={styles.setupGuide}>
          <summary>How to enable the MCP or plugin</summary>
          <ol>
            <li>Install the package, then run <code>codex-usage-tracker setup</code>.</li>
            <li>Restart Codex or open a fresh task when setup asks you to.</li>
            <li>Paste one of the prompts below into Codex and ask it to open the evidence.</li>
          </ol>
        </details>
        <div className={styles.promptRows}>
          {suggestedPrompts.map(item => (
            <article aria-label={item.title} className={styles.promptRow} key={item.title}>
              <div>
                <h3>{item.title}</h3>
                <p>{item.prompt}</p>
              </div>
              <Button
                variant="secondary"
                onClick={() => void copyPrompt(item.prompt, 'Prompt copied')}
                title={followUpPromptHelp}
              >
                <Copy size={15} /> Copy prompt
              </Button>
            </article>
          ))}
        </div>
        <p className={styles.copyStatus} role="status" aria-live="polite">{copyStatus}</p>
      </section>

      <section className={styles.section} aria-label="Recent findings">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Bounded persisted evidence</p>
            <h2>Recent findings</h2>
          </div>
          <span>Up to 3 high-confidence findings</span>
        </div>
        {home.findings.length ? (
          <div className={styles.findings}>
            {home.findings.map(finding => (
              <article className={styles.finding} key={finding.finding_id}>
                <div className={styles.cardHeading}>
                  <h3>{finding.title}</h3>
                  <StatusBadge tone="positive">High confidence</StatusBadge>
                </div>
                <p>{finding.summary}</p>
                <strong>{finding.action}</strong>
                <div className={styles.inlineActions}>
                  <Button variant="secondary" onClick={() => onOpenCall(finding.evidence.record_id)}>
                    Open evidence <ArrowRight size={15} />
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => void copyPrompt(finding.follow_up_prompt, 'Follow-up copied')}
                    title={followUpPromptHelp}
                  >
                    <Copy size={15} /> Copy follow-up
                  </Button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.empty}>No high-confidence findings are persisted for the current index.</p>
        )}
      </section>
    </div>
  );
}

function emptyScopeUsageMetrics(): OverviewLoadedMetrics {
  return {
    basis: 'scope',
    hasInputTokens: false,
    hasPricingCoverage: false,
    calls: 0,
    totalTokens: 0,
    cachedInputTokens: 0,
    uncachedInputTokens: 0,
    outputTokens: 0,
    reasoningOutputTokens: 0,
    cachePercent: 0,
    estimatedCostUsd: 0,
    estimatedCredits: 0,
  };
}

function homeUsageMetrics(
  summary: HomeSummaryPayload | undefined,
): OverviewLoadedMetrics | null {
  const metrics = summary?.usage_metrics;
  if (!metrics) return null;
  return {
    basis: 'scope',
    hasInputTokens: metrics.input_tokens > 0,
    hasPricingCoverage: metrics.pricing_coverage > 0,
    calls: metrics.calls,
    totalTokens: metrics.total_tokens,
    cachedInputTokens: metrics.cached_input_tokens,
    uncachedInputTokens: metrics.uncached_input_tokens,
    outputTokens: metrics.output_tokens,
    reasoningOutputTokens: metrics.reasoning_output_tokens,
    cachePercent: metrics.input_tokens > 0
      ? (metrics.cached_input_tokens / metrics.input_tokens) * 100
      : 0,
    estimatedCostUsd: metrics.estimated_cost_usd,
    estimatedCredits: metrics.usage_credits,
  };
}
