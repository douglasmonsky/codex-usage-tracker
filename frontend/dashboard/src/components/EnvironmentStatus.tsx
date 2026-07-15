import type { DashboardBootPayload } from '../api/types';
import type { ShellI18n } from '../app/i18n';

type EnvironmentStatusProps = {
  canUseLiveApi: boolean;
  payload: DashboardBootPayload | null;
  shellI18n: ShellI18n;
};

type EnvironmentStatusItem = {
  label: string;
  state: 'ready' | 'missing' | 'warn' | 'neutral';
  title: string;
};

const nonActionableParserDiagnostics = new Set(['duplicate_cumulative_total']);

export function EnvironmentStatus({ canUseLiveApi, payload, shellI18n }: EnvironmentStatusProps) {
  const items = environmentStatusItems(payload, canUseLiveApi, shellI18n);
  return (
    <section className="environment-status" aria-label={shellI18n.t('aria.dashboard_status', 'Dashboard status')}>
      <span className="environment-status-title">{shellI18n.t('aria.dashboard_status', 'Dashboard status')}</span>
      <div className="environment-status-grid">
        {items.map(item => (
          <span key={item.label} className="environment-chip" data-state={item.state} title={item.title}>
            {item.label}
          </span>
        ))}
      </div>
    </section>
  );
}

function environmentStatusItems(
  payload: DashboardBootPayload | null,
  canUseLiveApi: boolean,
  shellI18n: ShellI18n,
): EnvironmentStatusItem[] {
  const parserDiagnostics = parserDiagnosticsItem(payload?.parser_diagnostics, shellI18n);
  return [
    {
      label: shellI18n.t('badge.unofficial_project', 'Unofficial project'),
      state: 'neutral',
      title: shellI18n.t(
        'badge.unofficial_project_title',
        'Codex Usage Tracker is independent and is not made by, affiliated with, endorsed by, sponsored by, or supported by OpenAI. OpenAI and Codex are trademarks of OpenAI.',
      ),
    },
    {
      label: canUseLiveApi ? `${shellI18n.t('badge.live', 'Live')} API` : shellI18n.t('badge.static', 'Static'),
      state: canUseLiveApi ? 'ready' : 'warn',
      title: canUseLiveApi ? 'Local API token present for refresh actions.' : 'Static embedded snapshot; live refresh is unavailable.',
    },
    pricingStatusItem(payload, shellI18n),
    allowanceStatusItem(payload, shellI18n),
    privacyStatusItem(payload, shellI18n),
    dedupeStatusItem(payload),
    ...(parserDiagnostics ? [parserDiagnostics] : []),
  ];
}

function dedupeStatusItem(payload: DashboardBootPayload | null): EnvironmentStatusItem {
  const summary = payload?.dedupe;
  const excluded = Number(summary?.excluded_copied_rows || 0);
  const canonical = Number(summary?.canonical_rows || 0);
  const physical = Number(summary?.physical_rows || 0);
  return {
    label: `Deduped · ${excluded.toLocaleString()} copied excluded`,
    state: 'ready',
    title: `Billable totals use ${canonical.toLocaleString()} canonical rows while preserving ${physical.toLocaleString()} physical source rows.`,
  };
}

function pricingStatusItem(payload: DashboardBootPayload | null, shellI18n: ShellI18n): EnvironmentStatusItem {
  const configured = Boolean(payload?.pricing_configured);
  const warning = payload?.pricing_snapshot_warning?.trim() ?? '';
  const source = sourceLabel(payload?.pricing_source);
  return {
    label: configured ? shellI18n.t('badge.costs', 'Costs') : shellI18n.t('badge.no_costs', 'No costs'),
    state: configured ? (warning ? 'warn' : 'ready') : 'missing',
    title: configured
      ? [source || 'Pricing configured', warning].filter(Boolean).join(' - ')
      : shellI18n.t('pricing.configure_hint', 'Run codex-usage-tracker update-pricing to configure estimated costs.'),
  };
}

function allowanceStatusItem(payload: DashboardBootPayload | null, shellI18n: ShellI18n): EnvironmentStatusItem {
  const allowanceError = payload?.allowance_error?.trim() ?? '';
  const rateCardError = payload?.rate_card_error?.trim() ?? '';
  const source = sourceLabel(payload?.allowance_source) || 'Codex credit rates';
  if (allowanceError) {
    return {
      label: shellI18n.t('state.allowance_config_error', 'Allowance config error'),
      state: 'missing',
      title: `Config error: ${allowanceError}`,
    };
  }
  if (rateCardError) {
    return {
      label: 'Rate-card error',
      state: 'missing',
      title: `Rate-card error: ${rateCardError}`,
    };
  }
  if (payload?.allowance_configured) {
    return {
      label: shellI18n.t('state.allowance_configured', 'Allowance configured'),
      state: 'ready',
      title: source,
    };
  }
  if (payload?.rate_card_configured) {
    return {
      label: 'Credit rates loaded',
      state: 'ready',
      title: source,
    };
  }
  return {
    label: shellI18n.t('action.set_limits', 'Set limits'),
    state: 'warn',
    title: 'No local allowance windows are configured.',
  };
}

function privacyStatusItem(payload: DashboardBootPayload | null, shellI18n: ShellI18n): EnvironmentStatusItem {
  const projectPrivacy = payload?.project_metadata_privacy;
  const mode = projectPrivacy?.mode || payload?.privacy_mode || 'normal';
  const normal = mode === 'normal';
  const flags = [
    projectPrivacy?.cwd_redacted ? 'cwd redacted' : '',
    projectPrivacy?.project_names_redacted ? 'project names redacted' : '',
    projectPrivacy?.git_remote_label_hidden ? 'git remote hidden' : '',
    projectPrivacy?.relative_cwd_hidden ? 'relative cwd hidden' : '',
    projectPrivacy?.git_branch_hidden ? 'git branch hidden' : '',
    projectPrivacy?.tags_hidden ? 'tags hidden' : '',
  ].filter(Boolean);
  return {
    label: normal
      ? shellI18n.t('badge.metadata_normal', 'Metadata normal')
      : formatI18nTemplate(shellI18n.t('badge.metadata_mode', 'Metadata {mode}'), { mode }),
    state: normal ? 'ready' : 'warn',
    title: normal ? 'Project metadata is shown normally.' : [`Metadata mode: ${mode}`, ...flags].join(' - '),
  };
}

function parserDiagnosticsItem(
  parserDiagnostics: DashboardBootPayload['parser_diagnostics'],
  shellI18n: ShellI18n,
): EnvironmentStatusItem | null {
  const entries = Object.entries(parserDiagnostics ?? {}).filter(
    ([key, value]) => Number(value || 0) > 0 && !nonActionableParserDiagnostics.has(key),
  );
  if (!entries.length) return null;
  const total = entries.reduce((sum, [, value]) => sum + Number(value || 0), 0);
  const entryText = entries.map(([key, value]) => `${key}=${Number(value || 0)}`).join(', ');
  return {
    label: shellI18n.t('badge.parser_warnings', 'Parser warnings'),
    state: 'missing',
    title: formatI18nTemplate(
      shellI18n.t(
        'parser.warnings_title',
        'Latest refresh reported {count} parser diagnostics: {entries}. Run codex-usage-tracker inspect-log <path> to investigate schema drift.',
      ),
      { count: total.toLocaleString(), entries: entryText },
    ),
  };
}

function sourceLabel(source: DashboardBootPayload['pricing_source']): string {
  if (!source) return '';
  if (typeof source === 'string') return source;
  const label = source.label ?? source.name ?? source.type ?? source.path ?? '';
  return typeof label === 'string' ? label : '';
}

function formatI18nTemplate(template: string, values: Record<string, string>): string {
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (match, key) => values[key] ?? match);
}
