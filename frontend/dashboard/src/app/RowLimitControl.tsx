import { X } from 'lucide-react';
import { rowLimitMin, rowLimitNoCap, rowLimitStep, rowLimitValueLabel } from './rowLimit';

type RowLimitControlProps = {
  canLoadAllRows: boolean;
  canUseLiveApi: boolean;
  finitePendingLoadLimit: number;
  hasMoreRows: boolean;
  loadLabel: string;
  loadMoreLabel: string;
  pendingLoadLimit: number;
  pendingLoadLimitUncapped: boolean;
  refreshProgressPercent: number | null;
  refreshProgressText: string;
  refreshing: boolean;
  rowLimitChanged: boolean;
  rowLimitSliderMax: number;
  rowLimitSliderValue: number;
  rowLoadModeLabel: string;
  rowLoadStatus: string;
  onApply(): void;
  onCancel(): void | Promise<void>;
  onDraftChange(value: string): void;
  onLoadAll(): void;
  onLoadMore(): void;
  onNoCapChange(enabled: boolean): void;
  onSliderChange(value: string): void;
};

export function RowLimitControl(props: RowLimitControlProps) {
  const disabled = props.refreshing || !props.canUseLiveApi;

  return (
    <div className="row-limit-control" aria-label="Row limit control">
      <div className="row-limit-heading">
        <span>Rows loaded</span>
        <strong>{rowLimitValueLabel(props.pendingLoadLimit)}</strong>
      </div>
      <div className={`row-limit-status${props.refreshing ? ' is-loading' : ''}`} role="status" aria-live="polite">
        {props.refreshing ? (
          <>
            <span className="row-loading-dot" aria-hidden="true" />
            <span>{props.refreshProgressText}</span>
          </>
        ) : (
          <>
            <span>{props.rowLoadModeLabel}</span>
            <span>{props.rowLoadStatus}</span>
          </>
        )}
      </div>
      <div className="row-limit-range-meta">
        <span>Quick range</span>
        <span>{props.pendingLoadLimitUncapped ? 'No cap enabled' : 'No fixed max'}</span>
      </div>
      <input
        aria-label="Rows to load slider"
        aria-valuetext={
          props.pendingLoadLimitUncapped
            ? 'No row cap; move slider or type a count to restore a finite limit'
            : `${props.finitePendingLoadLimit.toLocaleString()} rows; slider expands as needed, or type any count`
        }
        type="range"
        min={rowLimitMin}
        max={props.rowLimitSliderMax}
        step={rowLimitStep}
        value={props.rowLimitSliderValue}
        onChange={event => props.onSliderChange(event.target.value)}
        disabled={disabled}
      />
      <div className="row-limit-entry">
        <input
          aria-label="Rows to load"
          type="number"
          min={rowLimitNoCap}
          step={rowLimitStep}
          value={props.pendingLoadLimit}
          onChange={event => props.onDraftChange(event.target.value)}
          aria-describedby="row-limit-entry-help"
          disabled={disabled}
        />
        <label className="row-limit-no-cap">
          <input
            aria-label="No row cap"
            type="checkbox"
            checked={props.pendingLoadLimitUncapped}
            onChange={event => props.onNoCapChange(event.target.checked)}
            disabled={disabled}
          />
          <span>No cap</span>
        </label>
        <button type="button" onClick={props.onApply} disabled={disabled || !props.rowLimitChanged}>
          {props.pendingLoadLimitUncapped ? 'Load all' : props.loadLabel}
        </button>
      </div>
      {props.refreshing ? (
        <div className="row-load-progress" aria-label="Row loading progress">
          <div
            className="row-load-progress-track"
            role="progressbar"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={props.refreshProgressPercent ?? undefined}
          >
            <span style={{ width: `${props.refreshProgressPercent ?? 8}%` }} />
          </div>
          <span>
            {props.refreshProgressPercent === null ? 'Preparing...' : `${Math.round(props.refreshProgressPercent)}% loaded`}
            <button
              className="icon-button"
              type="button"
              onClick={() => void props.onCancel()}
              aria-label="Cancel refresh"
              title="Cancel refresh"
            >
              <X size={13} />
            </button>
          </span>
        </div>
      ) : null}
      <button className="row-limit-load-all" type="button" onClick={props.onLoadAll} disabled={!props.canLoadAllRows}>
        Load all rows
      </button>
      <p id="row-limit-entry-help" className="row-limit-hint">
        Use Load all rows for the full history, or type any finite row count.
      </p>
      <div className="row-limit-load-more">
        <span>{props.rowLoadStatus}</span>
        <button type="button" onClick={props.onLoadMore} disabled={disabled || !props.hasMoreRows}>
          {props.loadMoreLabel}
        </button>
      </div>
    </div>
  );
}
