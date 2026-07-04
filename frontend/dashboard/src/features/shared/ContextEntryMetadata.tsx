import type { CallContextEntry } from '../../api/types';
import { formatNumber } from './format';

export function ContextEntryMetadata({ entry }: { entry: CallContextEntry }) {
  const chips = contextEntryChips(entry);
  if (!chips.length) return null;
  return (
    <div className="context-entry-chips" aria-label="Evidence entry metadata">
      {chips.map(chip => (
        <span key={`${chip.label}-${chip.value}`} title={chip.title}>
          {chip.label}: {chip.value}
        </span>
      ))}
    </div>
  );
}

function contextEntryChips(entry: CallContextEntry): Array<{ label: string; value: string; title?: string }> {
  const chips: Array<{ label: string; value: string; title?: string }> = [];
  const timing = entry.action_timing;
  if (timing?.since_turn_start_ms !== undefined) {
    chips.push({ label: 'T+', value: formatMilliseconds(timing.since_turn_start_ms), title: 'Elapsed since selected turn start' });
  }
  if (timing?.since_previous_entry_ms !== undefined) {
    chips.push({ label: 'Gap', value: formatMilliseconds(timing.since_previous_entry_ms), title: 'Gap since previous evidence entry' });
  }
  if (timing?.reported_duration_ms !== undefined) {
    chips.push({
      label: 'Duration',
      value: formatMilliseconds(timing.reported_duration_ms),
      title: timing.duration_source || 'Duration reported by this event',
    });
  }
  const lastUsage = entry.token_usage?.last_token_usage;
  if (lastUsage) {
    chips.push({ label: 'Entry tokens', value: tokenUsageChip(lastUsage), title: 'Token usage reported for this evidence entry' });
  }
  const totalUsage = entry.token_usage?.total_token_usage;
  if (totalUsage) {
    chips.push({
      label: 'Session tokens',
      value: tokenUsageChip(totalUsage),
      title: 'Cumulative token usage reported by this evidence entry',
    });
  }
  if (entry.compaction?.replacement_history_available) {
    chips.push({
      label: 'Compaction',
      value: `${formatNumber(entry.compaction.replacement_history?.length ?? 0)} replacement entries`,
      title: 'Compaction replacement history is available for this entry',
    });
  }
  if (entry.tool_output_omitted) {
    chips.push({ label: 'Tool output', value: 'omitted', title: 'Tool output omitted until explicitly requested' });
  }
  return chips;
}

function tokenUsageChip(usage: NonNullable<CallContextEntry['token_usage']>['last_token_usage']): string {
  const input = Number(usage?.input_tokens ?? 0);
  const cached = Number(usage?.cached_input_tokens ?? 0);
  const uncached = Number(usage?.uncached_input_tokens ?? Math.max(input - cached, 0));
  const output = Number(usage?.output_tokens ?? 0);
  const total = Number(usage?.total_tokens ?? input + output);
  return `${formatNumber(total)} total · ${formatNumber(uncached)} uncached`;
}

function formatMilliseconds(value: number): string {
  if (!Number.isFinite(value)) return '0ms';
  if (value < 1_000) return `${Math.round(value)}ms`;
  const seconds = value / 1_000;
  return seconds >= 10 ? `${seconds.toFixed(0)}s` : `${seconds.toFixed(1)}s`;
}
