import type { ThreadCallSortDirection, ThreadCallSortKey } from './threadsUrlState';
import styles from './ThreadAccordionGrid.module.css';

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
        <select
          aria-label="Sort thread calls"
          value={callSort}
          onChange={event => onCallSortChange(event.target.value)}
        >
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
