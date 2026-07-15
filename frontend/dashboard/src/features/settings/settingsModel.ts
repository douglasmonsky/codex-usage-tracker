import type { DashboardBootPayload } from '../../api/types';

const nonActionableParserDiagnostics = new Set(['duplicate_cumulative_total']);

export type SourceHealthRow = { label: string; value: string; issue: boolean };
export type AllowanceWindowRow = { source: string; label: string; value: string };

export function allowanceWindowSummary(payload: DashboardBootPayload | null): AllowanceWindowRow[] {
  const rows = [...observedUsageWindowRows(payload?.observed_usage), ...configuredAllowanceWindowRows(payload?.allowance_windows)];
  return rows.length ? rows : [{ source: 'allowance', label: 'Allowance config', value: 'No allowance windows configured' }];
}

function observedUsageWindowRows(observedUsage: DashboardBootPayload['observed_usage']): AllowanceWindowRow[] {
  const windows = Array.isArray(observedUsage?.windows) ? observedUsage.windows : [];
  if (!observedUsage?.available || !windows.length) return [];
  return weeklyFirst(windows).map(window => {
    const used = numericValue(window.used_percent);
    const remaining = used === null ? null : Math.max(0, Math.min(100, 100 - used));
    return {
      source: 'observed',
      label: `Observed ${shortLabel(window.label || window.key, 'Usage')}`,
      value: [remaining === null ? '' : `${formatPercent(remaining)} remaining`, used === null ? '' : `${formatPercent(used)} used`, resetLabel(window.resets_at)].filter(Boolean).join(' · ') || 'Observed usage available',
    };
  });
}

function configuredAllowanceWindowRows(windows: DashboardBootPayload['allowance_windows']): AllowanceWindowRow[] {
  if (!Array.isArray(windows) || !windows.length) return [];
  return weeklyFirst(windows).map(window => {
    const remainingPercent = numericValue(window.remaining_percent);
    const remainingCredits = numericValue(window.remaining_credits);
    const totalCredits = numericValue(window.total_credits);
    return {
      source: 'configured',
      label: `Configured ${shortLabel(window.label || window.key, 'Window')}`,
      value: [remainingPercent === null ? '' : `${formatPercent(remainingPercent)} remaining`, remainingCredits === null ? '' : `${formatNumber(remainingCredits)} cr left`, totalCredits === null ? '' : `${formatNumber(totalCredits)} cr total`, resetLabel(window.reset_at)].filter(Boolean).join(' · ') || 'Configured allowance window',
    };
  });
}

function weeklyFirst<T extends { key?: unknown; label?: unknown; window_minutes?: unknown }>(windows: T[]): T[] {
  return [...windows].sort((left, right) => Number(isWeeklyWindow(right)) - Number(isWeeklyWindow(left)));
}

function isWeeklyWindow(window: { key?: unknown; label?: unknown; window_minutes?: unknown }): boolean {
  const minutes = numericValue(window.window_minutes);
  const label = `${window.key ?? ''} ${window.label ?? ''}`.toLowerCase();
  return minutes === 10_080 || /\b(weekly|week|7d|7-day|7 day)\b/.test(label);
}

export function allowanceWindowSubtitle(payload: DashboardBootPayload | null): string {
  const usage = payload?.observed_usage;
  if (!usage?.available) return 'Manual allowance windows and live observed usage';
  return [usage.source || 'token_count.rate_limits', usage.plan_type ? `plan ${usage.plan_type}` : '', usage.limit_id ? `limit ${usage.limit_id}` : '', usage.observed_at ? `observed ${formatStableTimestamp(usage.observed_at)}` : ''].filter(Boolean).join(' · ');
}

export function sourceHealthSummary(payload: DashboardBootPayload | null): SourceHealthRow[] {
  const pricingWarning = payload?.pricing_snapshot_warning || '';
  const allowanceError = payload?.allowance_error || '';
  const rateCardError = payload?.rate_card_error || '';
  const parserDiagnostics = parserDiagnosticsLabel(payload?.parser_diagnostics);
  const metadataPrivacy = projectMetadataPrivacyLabel(payload?.project_metadata_privacy, payload?.privacy_mode);
  const dedupe = payload?.dedupe;
  const dedupeLabel = `${formatNumber(Number(dedupe?.excluded_copied_rows || 0))} copied rows excluded; ${formatNumber(Number(dedupe?.physical_rows || 0))} physical rows preserved`;
  return [
    { label: 'Pricing snapshot', value: pricingWarning || (payload?.pricing_configured ? 'Configured' : 'Not configured'), issue: Boolean(pricingWarning) || !payload?.pricing_configured },
    { label: 'Allowance config', value: allowanceError ? `Config error: ${allowanceError}` : (payload?.allowance_configured ? 'Configured' : 'Not configured'), issue: Boolean(allowanceError) || !payload?.allowance_configured },
    { label: 'Rate card', value: rateCardError ? `Rate-card error: ${rateCardError}` : (payload?.rate_card_configured ? 'Loaded' : 'Not loaded'), issue: Boolean(rateCardError) || !payload?.rate_card_configured },
    { label: 'Parser diagnostics', value: parserDiagnostics, issue: parserDiagnostics !== 'No parser warnings' },
    { label: 'Usage deduplication', value: dedupeLabel, issue: false },
    { label: 'Project metadata', value: metadataPrivacy, issue: metadataPrivacy !== 'Normal metadata' },
  ];
}

function parserDiagnosticsLabel(diagnostics: DashboardBootPayload['parser_diagnostics']): string {
  const entries = Object.entries(diagnostics ?? {}).filter(([key, value]) => Number(value || 0) > 0 && !nonActionableParserDiagnostics.has(key));
  if (!entries.length) return 'No parser warnings';
  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
  return `${formatNumber(total)} parser diagnostics: ${entries.map(([key, value]) => `${key}=${Number(value || 0)}`).join(', ')}`;
}

export function projectMetadataPrivacyLabel(metadata: DashboardBootPayload['project_metadata_privacy'], fallbackMode?: string): string {
  const mode = metadata?.mode || fallbackMode || 'normal';
  if (mode === 'normal') return 'Normal metadata';
  const flags = [metadata?.cwd_redacted ? 'cwd redacted' : '', metadata?.project_names_redacted ? 'project names redacted' : '', metadata?.git_remote_label_hidden ? 'git remote hidden' : '', metadata?.relative_cwd_hidden ? 'relative cwd hidden' : '', metadata?.git_branch_hidden ? 'git branch hidden' : '', metadata?.tags_hidden ? 'tags hidden' : '', metadata?.aliases_preserved ? 'aliases preserved' : ''].filter(Boolean);
  return flags.length ? `${mode}: ${flags.join(', ')}` : mode;
}

export function sourceLabel(source: DashboardBootPayload['pricing_source']): string {
  if (!source) return '';
  if (typeof source === 'string') return source;
  const label = source.label ?? source.name ?? source.type ?? source.path ?? '';
  return typeof label === 'string' ? label : '';
}

function numericValue(value: unknown): number | null { return typeof value === 'number' && Number.isFinite(value) ? value : null; }
function formatPercent(value: number): string { return `${value.toFixed(Math.abs(value) >= 10 ? 0 : 1)}%`; }
function shortLabel(value: string | undefined, fallback: string): string { return value?.trim() || fallback; }
function formatNumber(value: number): string { return value.toLocaleString(); }
function resetLabel(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  const timestamp = typeof value === 'number' ? value * 1000 : Date.parse(value);
  return Number.isFinite(timestamp) ? `resets ${formatStableTimestamp(timestamp)}` : '';
}
function formatStableTimestamp(value: string | number): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}
