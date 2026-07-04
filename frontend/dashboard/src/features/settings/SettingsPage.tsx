import { AlertTriangle, Database, History, LockKeyhole, RefreshCw, ShieldCheck } from 'lucide-react';

import type { DashboardBootPayload, DashboardModel } from '../../api/types';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';

type HistoryScope = 'active' | 'all';

const nonActionableParserDiagnostics = new Set(['duplicate_cumulative_total']);

type SettingsPageProps = {
  model: DashboardModel;
  payload: DashboardBootPayload | null;
  historyScope: HistoryScope;
  loadLimit: number;
  loadedRowCount: number;
  totalAvailableRows: number;
  canUseLiveApi: boolean;
  autoRefreshEnabled: boolean;
  refreshState: string;
};

export function SettingsPage({
  model,
  payload,
  historyScope,
  loadLimit,
  loadedRowCount,
  totalAvailableRows,
  canUseLiveApi,
  autoRefreshEnabled,
  refreshState,
}: SettingsPageProps) {
  const contextRuntime = model.contextRuntime;
  const sourceSummary = sourceLabel(payload?.pricing_source) || 'local pricing config';
  const allowanceSummary = sourceLabel(payload?.allowance_source) || 'local allowance config';
  const privacyMode = payload?.privacy_mode || 'aggregate-only snapshot';
  const metadataPrivacySummary = projectMetadataPrivacyLabel(payload?.project_metadata_privacy, payload?.privacy_mode);
  const rawContextSummary = contextRuntime.contextApiEnabled
    ? 'Explicit localhost request, selected call only'
    : 'Disabled until context API is enabled';
  const liveApiSummary = canUseLiveApi ? 'Local API token present' : 'Static embedded snapshot';
  const loadedLabel = `${formatNumber(loadedRowCount)} of ${formatNumber(totalAvailableRows || loadedRowCount)}`;
  const sourceHealthRows = sourceHealthSummary(payload);
  const allowanceWindowRows = allowanceWindowSummary(payload);

  return (
    <div className="page-grid">
      <div className="page-title-row">
        <div>
          <h1>Settings</h1>
          <p>Local dashboard runtime, source, and privacy state.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label={canUseLiveApi ? 'Live API available' : 'Static snapshot'} tone={canUseLiveApi ? 'green' : 'orange'} />
          <StatusBadge label={contextRuntime.contextApiEnabled ? 'Context API enabled' : 'Context API gated'} tone={contextRuntime.contextApiEnabled ? 'blue' : 'orange'} />
        </div>
      </div>

      <div className="dashboard-grid two">
        <Panel title="Runtime State" subtitle={refreshState}>
          <div className="setting-list">
            <span>
              <Database size={18} /> Rows loaded <strong>{loadedLabel}</strong>
            </span>
            <span>
              <History size={18} /> History scope <strong>{historyScope === 'all' ? 'All history' : 'Active history'}</strong>
            </span>
            <span>
              <RefreshCw size={18} /> Row request <strong>{loadLimit === 0 ? 'No cap' : formatNumber(loadLimit)}</strong>
            </span>
            <span>
              <RefreshCw size={18} /> Auto refresh <strong>{autoRefreshEnabled ? 'Enabled' : 'Paused'}</strong>
            </span>
          </div>
        </Panel>

        <Panel title="Data Sources" subtitle={canUseLiveApi ? 'Localhost API token present' : 'Embedded snapshot only'}>
          <div className="setting-list">
            <span>
              <Database size={18} /> Usage index <strong>{payload?.shell_boot ? 'served shell' : 'embedded payload'}</strong>
            </span>
            <span>
              <ShieldCheck size={18} /> Pricing <strong>{sourceSummary}</strong>
            </span>
            <span>
              <ShieldCheck size={18} /> Allowance <strong>{allowanceSummary}</strong>
            </span>
            <span>
              <LockKeyhole size={18} /> Raw context <strong>{contextRuntime.contextApiEnabled ? 'Explicit localhost request' : 'Disabled'}</strong>
            </span>
          </div>
        </Panel>

        <Panel title="Allowance Windows" className="span-all" subtitle={allowanceWindowSubtitle(payload)}>
          <div className="setting-list">
            {allowanceWindowRows.map(row => (
              <span key={`${row.source}-${row.label}`}>
                <RefreshCw size={18} /> {row.label} <strong>{row.value}</strong>
              </span>
            ))}
          </div>
        </Panel>

        <Panel title="Source Health" className="span-all" subtitle="Legacy dashboard warnings and metadata privacy">
          <div className="setting-list">
            {sourceHealthRows.map(row => (
              <span key={row.label}>
                {row.issue ? <AlertTriangle size={18} /> : <ShieldCheck size={18} />} {row.label} <strong>{row.value}</strong>
              </span>
            ))}
          </div>
        </Panel>

      <Panel title="Privacy Boundary" className="span-all" subtitle={privacyMode}>
        <div className="setting-list">
          <span>
            <ShieldCheck size={18} /> Payload mode <strong>{privacyMode}</strong>
          </span>
          <span>
            <ShieldCheck size={18} /> Project metadata <strong>{metadataPrivacySummary}</strong>
          </span>
          <span>
            <LockKeyhole size={18} /> Raw context <strong>{rawContextSummary}</strong>
          </span>
          <span>
            <Database size={18} /> Live requests <strong>{liveApiSummary}</strong>
          </span>
        </div>
        <ul className="compact-list">
          <li>Aggregate dashboard payloads avoid prompts, assistant text, and raw tool output.</li>
            <li>Raw context actions remain gated behind explicit Call Investigator controls.</li>
            <li>Live refresh and context requests stay local and require the dashboard API token.</li>
          </ul>
        </Panel>
      </div>
    </div>
  );
}

type SourceHealthRow = { label: string; value: string; issue: boolean };

type AllowanceWindowRow = { source: string; label: string; value: string };

function allowanceWindowSummary(payload: DashboardBootPayload | null): AllowanceWindowRow[] {
  const observedRows = observedUsageWindowRows(payload?.observed_usage);
  const configuredRows = configuredAllowanceWindowRows(payload?.allowance_windows);
  const rows = [...observedRows, ...configuredRows];
  if (rows.length) return rows;
  return [{ source: 'allowance', label: 'Allowance config', value: 'No allowance windows configured' }];
}

function observedUsageWindowRows(observedUsage: DashboardBootPayload['observed_usage']): AllowanceWindowRow[] {
  const windows = Array.isArray(observedUsage?.windows) ? observedUsage.windows : [];
  if (!observedUsage?.available || !windows.length) return [];
  return windows.map(window => {
    const usedPercent = numericValue(window.used_percent);
    const remaining = usedPercent === null ? null : Math.max(0, Math.min(100, 100 - usedPercent));
    const details = [
      remaining === null ? '' : `${formatPercent(remaining)} remaining`,
      usedPercent === null ? '' : `${formatPercent(usedPercent)} used`,
      resetLabel(window.resets_at),
    ].filter(Boolean);
    return {
      source: 'observed',
      label: `Observed ${shortLabel(window.label || window.key, 'Usage')}`,
      value: details.length ? details.join(' · ') : 'Observed usage available',
    };
  });
}

function configuredAllowanceWindowRows(windows: DashboardBootPayload['allowance_windows']): AllowanceWindowRow[] {
  if (!Array.isArray(windows) || !windows.length) return [];
  return windows.map(window => {
    const remainingPercent = numericValue(window.remaining_percent);
    const remainingCredits = numericValue(window.remaining_credits);
    const totalCredits = numericValue(window.total_credits);
    const details = [
      remainingPercent === null ? '' : `${formatPercent(remainingPercent)} remaining`,
      remainingCredits === null ? '' : `${formatCredits(remainingCredits)} left`,
      totalCredits === null ? '' : `${formatCredits(totalCredits)} total`,
      resetLabel(window.reset_at),
    ].filter(Boolean);
    return {
      source: 'configured',
      label: `Configured ${shortLabel(window.label || window.key, 'Window')}`,
      value: details.length ? details.join(' · ') : 'Configured allowance window',
    };
  });
}

function allowanceWindowSubtitle(payload: DashboardBootPayload | null): string {
  const observedUsage = payload?.observed_usage;
  if (observedUsage?.available) {
    const parts = [
      observedUsage.source || 'token_count.rate_limits',
      observedUsage.plan_type ? `plan ${observedUsage.plan_type}` : '',
      observedUsage.limit_id ? `limit ${observedUsage.limit_id}` : '',
      observedUsage.observed_at ? `observed ${formatStableTimestamp(observedUsage.observed_at)}` : '',
    ].filter(Boolean);
    return parts.join(' · ');
  }
  return 'Manual allowance windows and live observed usage';
}

function sourceHealthSummary(payload: DashboardBootPayload | null): SourceHealthRow[] {
  const pricingWarning = payload?.pricing_snapshot_warning || '';
  const allowanceError = payload?.allowance_error || '';
  const rateCardError = payload?.rate_card_error || '';
  const parserDiagnostics = parserDiagnosticsLabel(payload?.parser_diagnostics);
  const metadataPrivacy = projectMetadataPrivacyLabel(payload?.project_metadata_privacy, payload?.privacy_mode);
  return [
    {
      label: 'Pricing snapshot',
      value: pricingWarning || (payload?.pricing_configured ? 'Configured' : 'Not configured'),
      issue: Boolean(pricingWarning) || !payload?.pricing_configured,
    },
    {
      label: 'Allowance config',
      value: allowanceError
        ? `Config error: ${allowanceError}`
        : (payload?.allowance_configured ? 'Configured' : 'Not configured'),
      issue: Boolean(allowanceError) || !payload?.allowance_configured,
    },
    {
      label: 'Rate card',
      value: rateCardError
        ? `Rate-card error: ${rateCardError}`
        : (payload?.rate_card_configured ? 'Loaded' : 'Not loaded'),
      issue: Boolean(rateCardError) || !payload?.rate_card_configured,
    },
    {
      label: 'Parser diagnostics',
      value: parserDiagnostics,
      issue: parserDiagnostics !== 'No parser warnings',
    },
    {
      label: 'Project metadata',
      value: metadataPrivacy,
      issue: metadataPrivacy !== 'Normal metadata',
    },
  ];
}

function parserDiagnosticsLabel(parserDiagnostics: DashboardBootPayload['parser_diagnostics']): string {
  const entries = Object.entries(parserDiagnostics ?? {})
    .filter(([key, value]) => Number(value || 0) > 0 && !nonActionableParserDiagnostics.has(key));
  if (!entries.length) return 'No parser warnings';
  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
  return `${formatNumber(total)} parser diagnostics: ${entries.map(([key, value]) => `${key}=${Number(value || 0)}`).join(', ')}`;
}

function projectMetadataPrivacyLabel(
  projectMetadataPrivacy: DashboardBootPayload['project_metadata_privacy'],
  fallbackMode?: string,
): string {
  const mode = projectMetadataPrivacy?.mode || fallbackMode || 'normal';
  if (mode === 'normal') return 'Normal metadata';
  const flags = [
    projectMetadataPrivacy?.cwd_redacted ? 'cwd redacted' : '',
    projectMetadataPrivacy?.project_names_redacted ? 'project names redacted' : '',
    projectMetadataPrivacy?.git_remote_label_hidden ? 'git remote hidden' : '',
    projectMetadataPrivacy?.relative_cwd_hidden ? 'relative cwd hidden' : '',
    projectMetadataPrivacy?.git_branch_hidden ? 'git branch hidden' : '',
    projectMetadataPrivacy?.tags_hidden ? 'tags hidden' : '',
    projectMetadataPrivacy?.aliases_preserved ? 'aliases preserved' : '',
  ].filter(Boolean);
  return flags.length ? `${mode}: ${flags.join(', ')}` : mode;
}

function numericValue(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function formatPercent(value: number): string {
  const digits = Math.abs(value) >= 10 ? 0 : 1;
  return `${value.toFixed(digits)}%`;
}

function formatCredits(value: number): string {
  return `${formatNumber(value)} cr`;
}

function resetLabel(value: number | string | null | undefined): string {
  if (value === null || value === undefined || value === '') return '';
  const timestamp = typeof value === 'number' ? value * 1000 : Date.parse(value);
  if (!Number.isFinite(timestamp)) return '';
  return `resets ${formatStableTimestamp(timestamp)}`;
}

function formatStableTimestamp(value: string | number): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return `${date.toISOString().slice(0, 16).replace('T', ' ')} UTC`;
}

function shortLabel(value: string | undefined, fallback: string): string {
  const label = value?.trim();
  return label || fallback;
}

function sourceLabel(source: DashboardBootPayload['pricing_source']): string {
  if (!source) return '';
  if (typeof source === 'string') return source;
  const label = source.label ?? source.name ?? source.type ?? source.path ?? '';
  return typeof label === 'string' ? label : '';
}

function formatNumber(value: number): string {
  return value.toLocaleString();
}
