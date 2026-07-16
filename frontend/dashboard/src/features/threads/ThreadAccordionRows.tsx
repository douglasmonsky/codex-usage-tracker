import { Copy, Search } from 'lucide-react';
import type { CallRow } from '../../api/types';
import { CallSignalPucks } from '../shared/tables';
import { formatCompact, money, pct } from '../shared/format';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';
import {
  callPricingStatusText,
  formatCallContextUse,
  formatCredits,
  timelineSeverityClass,
  timelineWidth,
} from './threadAnalysis';
import type { ThreadCallSortDirection, ThreadCallSortKey } from './threadsUrlState';
import styles from './ThreadsPage.module.css';

export type ThreadCallControlsProps = {
  callSort: ThreadCallSortKey;
  callSortDirection: ThreadCallSortDirection;
  onCallSortChange(value: string): void;
  onCallSortDirectionChange(value: string): void;
};

export function ThreadCallControls({
  callSort,
  callSortDirection,
  onCallSortChange,
  onCallSortDirectionChange,
}: ThreadCallControlsProps): React.ReactElement {
  return (
    <div className={styles.threadCallControls}>
      <label>
        <span>Sort calls</span>
        <select aria-label="Sort thread calls" value={callSort} onChange={event => onCallSortChange(event.target.value)}>
          <option value="newest">Newest</option>
          <option value="duration">Duration</option>
          <option value="gap">Previous gap</option>
          <option value="initiator">Initiator</option>
          <option value="model">Model</option>
          <option value="effort">Effort</option>
          <option value="tokens">Most tokens</option>
          <option value="cached">Cached input</option>
          <option value="uncached">Uncached input</option>
          <option value="output">Output</option>
          <option value="reasoning">Reasoning</option>
          <option value="cost">Highest cost</option>
          <option value="cache">Lowest cache</option>
        </select>
      </label>
      <label>
        <span>Direction</span>
        <select
          aria-label="Sort thread calls direction"
          value={callSortDirection}
          onChange={event => onCallSortDirectionChange(event.target.value)}
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>
    </div>
  );
}

export function ThreadCallEvidenceRow({
  call,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  call: CallRow;
  onOpenInvestigator(recordId: string): void;
  onCopyCallLink(recordId: string): void;
}): React.ReactElement {
  const openLabel = `Open investigator for thread call ${call.thread} ${call.model}`;
  const copyLabel = `Copy link for thread call ${call.thread} ${call.model}`;
  return (
    <div className={styles.threadCallEvidence}>
      <div className={styles.threadCallIdentity}>
        <span>{call.time}</span>
        <strong>{call.model} / {call.effort}</strong>
        <span>{formatCompact(call.totalTokens)} tokens · {pct(call.cachedPct)} cache · {money(call.cost)}</span>
      </div>
      <div className={styles.threadCallSignals}>
        <CallSignalPucks call={call} />
        <span>Context {formatCallContextUse(call)}</span>
        <span>{callPricingStatusText(call)}</span>
      </div>
      <span>{call.duration}</span>
      <span>Prev {call.previousCallGap}</span>
      <span>{call.initiator || 'unknown'} initiated · {formatCredits(call.credits)}</span>
      <div className={styles.threadCallActions}>
        <button
          className="table-action-button"
          type="button"
          aria-label={openLabel}
          onKeyDown={stopRowActionKeyDown}
          onClick={() => onOpenInvestigator(call.id)}
        >
          <Search size={14} aria-hidden="true" /> Open
        </button>
        <button
          className="table-action-button"
          type="button"
          aria-label={copyLabel}
          onKeyDown={stopRowActionKeyDown}
          onClick={() => onCopyCallLink(call.id)}
        >
          <Copy size={14} aria-hidden="true" /> Copy
        </button>
      </div>
      {call.recommendation ? <p className={styles.threadCallRecommendation}>{call.recommendation}</p> : null}
      <div className={styles.threadContextBar} role="img" aria-label={`Context use ${formatCallContextUse(call)}`}>
        <span className={timelineSeverityClass(call.contextWindowPct)} style={{ width: timelineWidth(call.contextWindowPct) }} />
      </div>
    </div>
  );
}
