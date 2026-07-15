import type { ColumnDef } from '@tanstack/react-table';
import { Copy, Search } from 'lucide-react';
import { useShellI18n } from '../../app/i18nContext';
import type { CallRow, ThreadRow } from '../../api/types';
import type { ColumnChoice } from '../../components/ColumnChooser';
import type { CsvColumn } from './exportCsv';
import { formatCompact, formatNumber, money, pct } from './format';
import { stopRowActionKeyDown } from './rowActionEvents';

export const callColumns: Array<ColumnDef<CallRow>> = [
  { id: 'time', accessorFn: call => Number(Date.parse(call.eventTimestamp || call.callStartedAt || call.rawTime || call.time)) || 0, header: 'Time', cell: info => info.row.original.time },
  { accessorKey: 'thread', header: 'Thread' },
  { accessorKey: 'model', header: 'Model' },
  {
    accessorKey: 'effort',
    header: 'Effort',
    cell: info => <span className={`pill effort-${String(info.getValue())}`}>{String(info.getValue())}</span>,
  },
  {
    accessorKey: 'input',
    header: 'Input Tokens',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'totalTokens',
    header: 'Total Tokens',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cachedInput',
    header: 'Cached Input',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'uncachedInput',
    header: 'Uncached Input',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'output',
    header: 'Output Tokens',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'reasoningOutput',
    header: 'Reasoning Output',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cachedPct',
    header: 'Cached %',
    cell: info => <span className="cache-pill">{pct(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cost',
    header: 'Est. Cost',
    cell: info => <span className="num">{money(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'credits',
    header: 'Codex Credits',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'contextWindowPct',
    header: 'Context %',
    cell: info => {
      const rawValue = info.getValue();
      const value = typeof rawValue === 'number' ? rawValue : Number.NaN;
      return <span className="num">{Number.isFinite(value) ? pct(value) : '-'}</span>;
    },
  },
  { accessorKey: 'duration', header: 'Duration' },
  {
    accessorKey: 'previousCallGap',
    header: 'Prev Gap',
    cell: info => <span className="num">{String(info.getValue())}</span>,
  },
  {
    accessorKey: 'initiator',
    header: 'Initiated',
    cell: info => <span className="status-badge blue">{String(info.getValue())}</span>,
  },
  {
    accessorKey: 'signal',
    header: 'Signals',
    cell: info => <CallSignalPucks call={info.row.original} />,
  },
];

export const callCsvColumns: Array<CsvColumn<CallRow>> = [
  { header: 'timestamp', value: row => row.eventTimestamp || row.rawTime || row.time },
  { header: 'thread', value: row => row.thread },
  { header: 'call_started_at', value: row => row.callStartedAt || row.rawTime || row.time },
  { header: 'call_duration_seconds', value: row => row.durationSeconds },
  { header: 'previous_call_event_timestamp', value: row => row.previousCallEventTimestamp },
  { header: 'previous_call_delta_seconds', value: row => row.previousCallGapSeconds },
  { header: 'initiated', value: row => row.initiator },
  { header: 'initiated_reason', value: row => row.initiatorReason },
  { header: 'project', value: row => row.project },
  { header: 'model', value: row => row.model },
  { header: 'effort', value: row => row.effort },
  { header: 'total_tokens', value: row => row.totalTokens },
  { header: 'input_tokens', value: row => row.input },
  { header: 'cached_input_tokens', value: row => row.cachedInput },
  { header: 'uncached_input_tokens', value: row => row.uncachedInput },
  { header: 'output_tokens', value: row => row.output },
  { header: 'reasoning_output_tokens', value: row => row.reasoningOutput },
  { header: 'estimated_cost_usd', value: row => row.cost.toFixed(6) },
  { header: 'usage_credits', value: row => row.credits.toFixed(6) },
  { header: 'cache_ratio', value: row => row.cachedPct.toFixed(2) },
  { header: 'context_window_percent', value: row => row.contextWindowPct?.toFixed(2) ?? '' },
  { header: 'pricing_model', value: row => row.pricingModel },
  { header: 'usage_credit_confidence', value: row => row.usageCreditConfidence },
  { header: 'recommendation', value: row => row.recommendation },
  { header: 'record_id', value: row => row.id },
  { header: 'thread_attachment', value: row => row.threadAttachmentLabel },
  { header: 'thread_source', value: row => row.threadSource },
  { header: 'parent_thread', value: row => row.parentThread },
  { header: 'session_id', value: row => row.sessionId },
  { header: 'turn_id', value: row => row.turnId },
  { header: 'parent_session_id', value: row => row.parentSessionId },
  { header: 'parent_session_updated_at', value: row => row.parentSessionUpdatedAt },
  { header: 'project_relative_cwd', value: row => row.projectRelativeCwd },
  { header: 'cwd', value: row => row.cwd },
  { header: 'source_file', value: row => row.sourceFile },
  { header: 'source_line', value: row => row.lineNumber ?? '' },
  { header: 'git_branch', value: row => row.gitBranch },
  { header: 'git_remote_label', value: row => row.gitRemoteLabel },
  { header: 'git_remote_hash', value: row => row.gitRemoteHash },
  { header: 'pricing_estimated', value: row => String(row.pricingEstimated) },
  { header: 'usage_credit_model', value: row => row.usageCreditModel },
  { header: 'usage_credit_source', value: row => row.usageCreditSource },
  { header: 'usage_credit_tier', value: row => row.usageCreditTier },
  { header: 'usage_credit_fetched_at', value: row => row.usageCreditFetchedAt },
  { header: 'usage_credit_note', value: row => row.usageCreditNote },
  { header: 'model_context_window', value: row => row.modelContextWindow ?? '' },
  { header: 'cumulative_total_tokens', value: row => row.cumulativeTotalTokens ?? '' },
  { header: 'estimated_cache_savings_usd', value: row => row.estimatedCacheSavings.toFixed(6) },
  { header: 'initiated_confidence', value: row => row.initiatorConfidence },
  { header: 'signal', value: row => row.signal },
  { header: 'tags', value: row => row.tags.join('|') },
  { header: 'efficiency_flags', value: row => row.efficiencyFlags.join('|') },
];

export type CallSignalPuck = {
  key: string;
  label: string;
  shortLabel: string;
};

export function callSignalPucks(call: CallRow, maxVisible = 3): { visible: CallSignalPuck[]; hidden: CallSignalPuck[] } {
  const signals = uniqueSignals([call.signal, ...call.efficiencyFlags]);
  const pucks = signals.map((signal, index) => ({
    key: `${signal}-${index}`,
    label: signalLabel(signal),
    shortLabel: signalPuckAbbreviation(signal),
  }));
  return {
    visible: pucks.slice(0, maxVisible),
    hidden: pucks.slice(maxVisible),
  };
}

export function CallSignalPucks({ call }: { call: CallRow }) {
  const i18n = useShellI18n();
  const { visible, hidden } = callSignalPucks(call);
  if (!visible.length) {
    return <span className="muted">None</span>;
  }

  const localizedPucks = visible.map(puck => ({ ...puck, label: i18n.translateText(puck.label), shortLabel: i18n.translateText(puck.shortLabel) }));
  const localizedHidden = hidden.map(puck => ({ ...puck, label: i18n.translateText(puck.label), shortLabel: i18n.translateText(puck.shortLabel) }));
  const hiddenLabel = localizedHidden.map(puck => puck.label).join('、');
  return (
    <span className="flags compact-flags" aria-label={i18n.language === 'zh-Hans' ? `信号：${[...localizedPucks, ...localizedHidden].map(puck => puck.label).join('、')}` : `Signals: ${[...visible, ...hidden].map(puck => puck.label).join(', ')}`}>
      {localizedPucks.map(puck => (
        <span key={puck.key} className="flag signal-puck" title={puck.label}>
          {puck.shortLabel}
        </span>
      ))}
      {localizedHidden.length ? (
        <span className="flag signal-puck more" title={hiddenLabel}>
          +{localizedHidden.length}
        </span>
      ) : null}
    </span>
  );
}

function uniqueSignals(values: string[]): string[] {
  const seen = new Set<string>();
  return values
    .map(value => value.trim())
    .filter(value => value && value !== 'aggregate')
    .filter(value => {
      const key = value.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

function signalLabel(signal: string): string {
  return signal
    .replace(/[-_]+/g, ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function signalPuckAbbreviation(signal: string): string {
  const normalized = signal.toLowerCase().replace(/[_\s]+/g, '-');
  const bySignal: Record<string, string> = {
    'cache-drop': 'CACHE',
    'cache-risk': 'CACHE',
    'context-bloat': 'CTX',
    'context-heavy': 'CTX',
    'elevated-context': 'CTX',
    'elevated-context-use': 'CTX',
    'estimated-pricing': 'EST',
    'expensive-low-output-call': 'LO',
    'high-context-use': 'CTX',
    'high-cost': '$',
    'high-estimated-cost': '$',
    'high-reasoning-share': 'RSN',
    'large-thread': 'BIG',
    'low-cache': 'CACHE',
    'low-cache-reuse': 'CACHE',
    'low-output': 'LO',
    'pricing-gap': 'PRICE',
    'reasoning-spike': 'RSN',
    'subagent-attribution': 'SUB',
  };
  if (bySignal[normalized]) return bySignal[normalized];

  const words = signalLabel(signal).split(/\s+/).filter(Boolean);
  if (!words.length) return '?';
  if (words.length === 1) return words[0].slice(0, 4).toUpperCase();
  return words
    .slice(0, 3)
    .map(word => word[0])
    .join('')
    .toUpperCase();
}

type CallActionColumnOptions = {
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink?: (recordId: string) => void;
  labelPrefix?: string;
};

export function callInvestigatorRowLabel(call: CallRow, labelPrefix = ''): string {
  return `Open call row in investigator for ${callActionTarget(call, labelPrefix)}`;
}

export function threadInvestigatorRowLabel(thread: ThreadRow): string {
  return thread.latestCallId ? `Open thread row latest call in investigator for ${thread.name}` : `No loaded call available for ${thread.name}`;
}

export function callActionColumn({
  onOpenInvestigator,
  onCopyCallLink,
  labelPrefix = '',
}: CallActionColumnOptions): ColumnDef<CallRow> {
  return {
    id: 'investigate',
    header: 'Investigate',
    size: 260,
    enableSorting: false,
    cell: info => (
      <CallActionCell
        call={info.row.original}
        labelPrefix={labelPrefix}
        onCopyCallLink={onCopyCallLink}
        onOpenInvestigator={onOpenInvestigator}
      />
    ),
  };
}

function CallActionCell({
  call,
  labelPrefix,
  onCopyCallLink,
  onOpenInvestigator,
}: {
  call: CallRow;
  labelPrefix: string;
  onCopyCallLink?: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
}) {
  const shellI18n = useShellI18n();
  const openInvestigatorLabel = shellI18n.t('button.open_investigator', 'Open investigator');
  const copyLinkLabel = shellI18n.t('button.copy_link', 'Copy link');
  const labelTarget = callActionTarget(call, labelPrefix);

  return (
    <div className="table-action-group">
<button
className="table-action-button"
type="button"
aria-label={`${openInvestigatorLabel} for ${labelTarget}`}
onKeyDown={stopRowActionKeyDown}
onClick={event => {
event.stopPropagation();
onOpenInvestigator(call.id);
        }}
      >
        <Search size={14} />
        {openInvestigatorLabel}
      </button>
      {onCopyCallLink ? (
<button
className="table-action-button"
type="button"
aria-label={`${copyLinkLabel} for ${labelTarget}`}
onKeyDown={stopRowActionKeyDown}
onClick={event => {
event.stopPropagation();
onCopyCallLink(call.id);
          }}
        >
          <Copy size={14} />
          {copyLinkLabel}
        </button>
      ) : null}
    </div>
  );
}

function callActionTarget(call: CallRow, labelPrefix: string): string {
  return `${labelPrefix} ${call.thread} ${call.model}`.trim();
}

export const threadColumns: Array<ColumnDef<ThreadRow>> = [
  { accessorKey: 'name', header: 'Thread' },
  { accessorKey: 'latestActivity', header: 'Latest' },
  {
    accessorKey: 'turns',
    header: 'Turns',
    cell: info => <span className="num">{formatNumber(Number(info.getValue()))}</span>,
  },
  { accessorKey: 'totalDuration', header: 'Duration' },
  {
    accessorKey: 'averageGap',
    header: 'Avg Gap',
    cell: info => <span className="num">{String(info.getValue())}</span>,
  },
  {
    accessorKey: 'initiatorSummary',
    header: 'Initiated',
    cell: info => <span className="status-badge blue">{String(info.getValue())}</span>,
  },
  {
    accessorKey: 'modelSummary',
    header: 'Models',
    cell: info => <span className="pill model-pill">{String(info.getValue())}</span>,
  },
  { accessorKey: 'effortSummary', header: 'Effort Mix' },
  {
    accessorKey: 'totalTokens',
    header: 'Total Tokens',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cachedInput',
    header: 'Cached Input',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'uncachedInput',
    header: 'Uncached Input',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'outputTokens',
    header: 'Output Tokens',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'reasoningOutput',
    header: 'Reasoning Output',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cost',
    header: 'Est. Cost',
    cell: info => <span className="num">{money(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'credits',
    header: 'Codex Credits',
    cell: info => <span className="num">{formatCompact(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'cachePct',
    header: 'Cache %',
    cell: info => <span className="cache-pill">{pct(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'contextPct',
    header: 'Context %',
    cell: info => {
      const value = info.getValue<number | null>();
      return <span className="num">{typeof value === 'number' ? pct(value) : '-'}</span>;
    },
  },
  {
    accessorKey: 'costPerCall',
    header: 'Cost / Call',
    cell: info => <span className="num">{money(Number(info.getValue()))}</span>,
  },
  {
    accessorKey: 'coldResumeRisk',
    header: 'Cold Resume Risk',
    cell: info => <span className={`status-badge ${riskTone(String(info.getValue()))}`}>{String(info.getValue())}</span>,
  },
  {
    accessorKey: 'productivity',
    header: 'Productivity',
    cell: info => <span className="score">{Number(info.getValue())}</span>,
  },
];

type ThreadActionColumnOptions = {
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink?: (recordId: string) => void;
};

export function threadActionColumn({ onOpenInvestigator, onCopyCallLink }: ThreadActionColumnOptions): ColumnDef<ThreadRow> {
  return {
    id: 'investigate',
    header: 'Investigate',
    size: 260,
    enableSorting: false,
    cell: info => {
      const thread = info.row.original;
      return (
        <div className="table-action-group">
          <button
            className="table-action-button"
            type="button"
            aria-label={`Open investigator for latest call in ${thread.name}`}
 onKeyDown={stopRowActionKeyDown}
            onClick={event => {
              event.stopPropagation();
              if (thread.latestCallId) {
                onOpenInvestigator(thread.latestCallId);
              }
            }}
            disabled={!thread.latestCallId}
          >
            <Search size={14} />
            Open
          </button>
          {onCopyCallLink ? (
            <button
              className="table-action-button"
              type="button"
 onKeyDown={stopRowActionKeyDown}
              aria-label={`Copy link for latest call in ${thread.name}`}
              onClick={event => {
                event.stopPropagation();
                if (thread.latestCallId) {
                  onCopyCallLink(thread.latestCallId);
                }
              }}
              disabled={!thread.latestCallId}
            >
              <Copy size={14} />
              Copy
            </button>
          ) : null}
        </div>
      );
    },
  };
}

export const threadColumnChoices: ColumnChoice[] = [
  { id: 'name', label: 'Thread', locked: true },
  { id: 'latestActivity', label: 'Latest' },
  { id: 'turns', label: 'Turns' },
  { id: 'totalDuration', label: 'Duration' },
  { id: 'averageGap', label: 'Avg Gap' },
  { id: 'initiatorSummary', label: 'Initiated' },
  { id: 'modelSummary', label: 'Models' },
  { id: 'effortSummary', label: 'Effort Mix' },
  { id: 'totalTokens', label: 'Total Tokens' },
  { id: 'cachedInput', label: 'Cached Input' },
  { id: 'uncachedInput', label: 'Uncached Input' },
  { id: 'outputTokens', label: 'Output Tokens' },
  { id: 'reasoningOutput', label: 'Reasoning Output' },
  { id: 'cost', label: 'Est. Cost' },
  { id: 'credits', label: 'Codex Credits' },
  { id: 'cachePct', label: 'Cache %' },
  { id: 'contextPct', label: 'Context %' },
  { id: 'costPerCall', label: 'Cost / Call' },
  { id: 'coldResumeRisk', label: 'Cold Resume Risk' },
  { id: 'productivity', label: 'Productivity' },
  { id: 'investigate', label: 'Investigate', locked: true },
];

function riskTone(value: string): 'green' | 'orange' | 'red' | 'neutral' {
  if (value === 'High') {
    return 'red';
  }
  if (value === 'Medium') {
    return 'orange';
  }
  if (value === 'Low') {
    return 'green';
  }
  return 'neutral';
}
