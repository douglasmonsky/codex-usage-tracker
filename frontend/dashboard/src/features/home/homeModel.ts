import type {
  ConversationalReadiness,
  DashboardBootPayload,
  HomeFindingPayload,
  HomeRecentEvidencePayload,
  HomeSummaryPayload,
} from '../../api/types';

const starterInvestigationPrompt =
  'Use codex-usage-tracker to summarize my recent usage, identify the highest-confidence issue, and cite the supporting evidence.';

type HomeStatusCard = {
  id: 'index' | 'mcp' | 'accounting' | 'pricing' | 'allowance';
  label: string;
  value: string;
  detail: string;
  tone: 'positive' | 'caution' | 'neutral';
};

export type HomeViewModel = {
  statusCards: HomeStatusCard[];
  findings: HomeFindingPayload[];
  recentEvidence: HomeRecentEvidencePayload[];
  starterPrompt: string;
};

export function buildHomeModel({
  payload,
  summary,
  readiness,
  now = new Date(),
}: {
  payload: DashboardBootPayload | null | undefined;
  summary: HomeSummaryPayload | undefined;
  readiness: ConversationalReadiness | undefined;
  now?: Date;
}): HomeViewModel {
  return {
    statusCards: [
      indexCard(payload, summary, now),
      mcpCard(readiness),
      accountingCard(payload, summary),
      pricingCard(payload, summary),
      allowanceCard(payload, summary),
    ],
    findings: (summary?.findings ?? [])
      .filter(finding => finding.confidence === 'high')
      .slice(0, 3),
    recentEvidence: (summary?.recent_evidence ?? []).slice(0, 5),
    starterPrompt: starterInvestigationPrompt,
  };
}

function indexCard(
  payload: DashboardBootPayload | null | undefined,
  summary: HomeSummaryPayload | undefined,
  now: Date,
): HomeStatusCard {
  const refreshedAt = summary?.latest_refresh_at ?? payload?.latest_refresh_at ?? '';
  const sourceRevision = summary?.source_revision || 'unversioned';
  const refreshTime = Date.parse(refreshedAt);
  if (!refreshedAt || !Number.isFinite(refreshTime)) {
    return {
      id: 'index', label: 'Index', value: 'Missing',
      detail: `Source ${sourceRevision} · refresh metadata unavailable`, tone: 'caution',
    };
  }
  const stale = now.getTime() - refreshTime > 24 * 60 * 60 * 1000;
  return {
    id: 'index',
    label: 'Index',
    value: stale ? 'Stale' : 'Fresh',
    detail: `Source ${sourceRevision} · refreshed ${formatTimestamp(refreshedAt)}`,
    tone: stale ? 'caution' : 'positive',
  };
}

function mcpCard(readiness: ConversationalReadiness | undefined): HomeStatusCard {
  const state = readiness?.state ?? 'unknown';
  const value = state === 'ready'
    ? 'Ready'
    : state === 'restart-required'
      ? 'Restart required'
      : state === 'unavailable'
        ? 'Unavailable'
        : 'Checking';
  const profile = readiness?.configured_profile || 'unknown';
  const runtime = readiness?.runtime_version_matches === false ? 'runtime mismatch' : 'runtime aligned';
  return {
    id: 'mcp',
    label: 'Conversational analysis',
    value,
    detail: `${profile} profile · ${runtime}`,
    tone: state === 'ready' ? 'positive' : state === 'unknown' ? 'neutral' : 'caution',
  };
}

function accountingCard(
  payload: DashboardBootPayload | null | undefined,
  summary: HomeSummaryPayload | undefined,
): HomeStatusCard {
  const accounting = summary?.accounting ?? payload?.dedupe ?? {};
  const physical = count(accounting.physical_rows);
  const canonical = count(accounting.canonical_rows);
  const excluded = count(accounting.excluded_copied_rows);
  return {
    id: 'accounting',
    label: 'Accounting',
    value: canonical ? `${formatNumber(canonical)} canonical` : 'No indexed calls',
    detail: `${formatNumber(physical)} physical · ${formatNumber(excluded)} copied excluded`,
    tone: canonical ? 'positive' : 'neutral',
  };
}

function pricingCard(
  payload: DashboardBootPayload | null | undefined,
  summary: HomeSummaryPayload | undefined,
): HomeStatusCard {
  const snapshot = summary?.pricing ?? payload?.pricing_snapshot;
  const configured = Boolean(payload?.pricing_configured || snapshot?.configured);
  if (!configured) {
    return {
      id: 'pricing', label: 'Pricing coverage', value: 'Missing',
      detail: 'No local pricing snapshot is configured', tone: 'caution',
    };
  }
  const estimated = count(snapshot?.estimated_model_count);
  const total = count(snapshot?.model_count);
  const partial = Boolean(payload?.pricing_snapshot_warning) || estimated > 0;
  const detail = total
    ? `${formatNumber(total)} configured models${estimated ? ` · ${formatNumber(estimated)} estimated` : ''}`
    : 'Local pricing snapshot configured';
  return {
    id: 'pricing', label: 'Pricing coverage', value: partial ? 'Partial' : 'Ready',
    detail, tone: partial ? 'caution' : 'positive',
  };
}

function allowanceCard(
  payload: DashboardBootPayload | null | undefined,
  summary: HomeSummaryPayload | undefined,
): HomeStatusCard {
  const allowance = summary?.allowance;
  const observedWindows = allowance?.observed_usage?.windows ?? [];
  const observed = preferredWindow(
    observedWindows.length ? observedWindows : payload?.observed_usage?.windows ?? [],
  );
  const used = finitePercent(observed?.used_percent);
  if (used !== null) {
    const remaining = Math.max(0, 100 - used);
    return {
      id: 'allowance', label: 'Allowance', value: `${formatPercent(remaining)} remaining`,
      detail: `${observed?.label || observed?.key || 'Observed'} · ${allowance?.observed_usage?.source || payload?.observed_usage?.source || 'local observation'}`,
      tone: remaining < 20 ? 'caution' : 'positive',
    };
  }
  const configuredWindows = allowance?.windows ?? [];
  const configured = preferredWindow(
    configuredWindows.length ? configuredWindows : payload?.allowance_windows ?? [],
  );
  const remaining = finitePercent(configured?.remaining_percent);
  if (remaining !== null) {
    return {
      id: 'allowance', label: 'Allowance', value: `${formatPercent(remaining)} remaining`,
      detail: configured?.label || configured?.key || 'Configured allowance',
      tone: remaining < 20 ? 'caution' : 'positive',
    };
  }
  return {
    id: 'allowance', label: 'Allowance', value: 'Not configured',
    detail: allowance?.error || payload?.allowance_error || 'No current allowance window is available', tone: 'neutral',
  };
}

function preferredWindow<T extends { key?: string; label?: string }>(windows: T[]): T | undefined {
  return windows.find(window => `${window.key ?? ''} ${window.label ?? ''}`.toLowerCase().includes('week'))
    ?? windows[0];
}

function finitePercent(value: unknown): number | null {
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) ? Math.min(100, Math.max(0, number)) : null;
}

function count(value: unknown): number {
  const number = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(number) ? Math.max(0, Math.trunc(number)) : 0;
}

function formatNumber(value: number): string {
  return value.toLocaleString('en-US');
}

function formatPercent(value: number): string {
  return `${Number.isInteger(value) ? value : value.toFixed(1)}%`;
}

function formatTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isFinite(date.getTime()) ? date.toLocaleString() : value;
}
