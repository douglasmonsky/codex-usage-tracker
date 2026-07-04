import { Copy } from 'lucide-react';

import type { CallRow } from '../../api/types';
import { formatCompact, pct } from './format';

type ThreadCallTimelineProps = {
  selectedCall: CallRow;
  calls: CallRow[];
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  className?: string;
  copyAriaContext: string;
  copyLabel?: string;
};

export function ThreadCallTimeline({
  selectedCall,
  calls,
  onOpenInvestigator,
  onCopyCallLink,
  className,
  copyAriaContext,
  copyLabel = 'Copy link',
}: ThreadCallTimelineProps) {
  const rows = calls.length ? calls : [selectedCall];
  const timeline = centeredTimeline(rows, selectedCall.id);
  const timelineClassName = ['thread-mini-timeline', className].filter(Boolean).join(' ');

  return (
    <ol className={timelineClassName}>
      {timeline.map(row => (
        <li key={row.id} className={row.id === selectedCall.id ? 'active' : ''}>
          <span>{row.time}</span>
          <strong>{row.model} / {row.effort}</strong>
          <em>{formatCompact(row.totalTokens)} tokens - {pct(row.cachedPct)} cache</em>
          <div className="thread-call-meta">
            <span>{row.initiator || 'unknown'}</span>
            <span>{row.duration}</span>
            <span>prev {row.previousCallGap}</span>
          </div>
          <div className="thread-call-flags">
            <span>Context {timelineContextLabel(row)}</span>
            <span>{timelinePricingStatus(row)}</span>
          </div>
          {row.recommendation ? <p className="thread-call-recommendation">{row.recommendation}</p> : null}
          <div className="thread-context-bar" title={`Context window ${timelineContextTitle(row)}`}>
            <span
              className={contextSeverity(row.contextWindowPct)}
              style={{ width: contextBarWidth(row.contextWindowPct) }}
            />
          </div>
          <div className="thread-call-actions table-action-group">
            <button
              className="table-action-button"
              type="button"
              onClick={() => onOpenInvestigator(row.id)}
              disabled={row.id === selectedCall.id}
            >
              Open
            </button>
            <button
              className="table-action-button"
              type="button"
              aria-label={`${copyLabel} for ${copyAriaContext} ${row.thread} ${row.model}`}
              onClick={() => onCopyCallLink(row.id)}
            >
              <Copy size={14} /> {copyLabel}
            </button>
          </div>
        </li>
      ))}
    </ol>
  );
}

function centeredTimeline(rows: CallRow[], selectedId: string): CallRow[] {
  if (rows.length <= 5) return rows;
  const selectedIndex = rows.findIndex(row => row.id === selectedId);
  if (selectedIndex < 0) return rows.slice(0, 5);
  const start = Math.max(0, Math.min(selectedIndex - 2, rows.length - 5));
  return rows.slice(start, start + 5);
}

function timelineContextLabel(call: CallRow): string {
  return call.contextWindowPct === null ? 'Not reported' : pct(call.contextWindowPct);
}

function timelineContextTitle(call: CallRow): string {
  if (call.contextWindowPct === null) return 'Not reported';
  const windowSize = call.modelContextWindow ? ` of ${formatCompact(call.modelContextWindow)}` : '';
  return `${pct(call.contextWindowPct)}${windowSize}`;
}

function timelinePricingStatus(call: CallRow): string {
  if (call.cost <= 0) return 'No configured price';
  return call.pricingEstimated ? 'Best-guess estimate' : 'Configured price';
}

function contextSeverity(value: number | null): 'low' | 'medium' | 'high' {
  const numeric = Number(value ?? 0);
  if (numeric >= 75) return 'high';
  if (numeric >= 50) return 'medium';
  return 'low';
}

function contextBarWidth(value: number | null): string {
  const numeric = Number(value ?? 0);
  const bounded = Math.max(0, Math.min(100, Number.isFinite(numeric) ? numeric : 0));
  return `${Math.round(bounded)}%`;
}
