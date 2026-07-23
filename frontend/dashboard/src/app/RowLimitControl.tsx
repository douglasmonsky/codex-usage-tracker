import { X } from 'lucide-react';

import type { LoadWindow } from './rowLimit';

type RowLimitControlProps = {
  canUseLiveApi: boolean;
  finitePendingLoadLimit: number;
  focusedScope: boolean;
  hasMoreRows: boolean;
  loadLabel: string;
  loadMoreLabel: string;
  loadWindow: LoadWindow;
  loadedRowCount: number;
  pendingLoadLimit: number;
  refreshProgressPercent: number | null;
  refreshProgressText: string;
  refreshing: boolean;
  rowLimitChanged: boolean;
  rowLimitSliderMax: number;
  rowLimitSliderValue: number;
  rowLoadModeLabel: string;
  rowLoadStatus: string;
  totalAvailableRows: number;
  onApply(): void;
  onCancel(): void | Promise<void>;
  onDraftChange(value: string): void;
  onLoadMore(): void;
  onSliderChange(value: string): void;
  onWindowChange(value: LoadWindow): void;
};

const windowOptions: Array<{ value: LoadWindow; label: string; ariaLabel: string }> = [
  { value: 'day', label: '24 hours', ariaLabel: 'Last 24h' },
  { value: 'week', label: '7 days', ariaLabel: 'Last 7 days' },
  { value: 'rows', label: 'Recent', ariaLabel: 'Recent rows' },
  { value: 'all', label: 'All time', ariaLabel: 'All time' },
];

export function RowLimitControl(props: RowLimitControlProps) {
  const disabled = props.refreshing || !props.canUseLiveApi;
  const isRecentRows = props.loadWindow === 'rows';
  const detailRowLabel = `${props.loadedRowCount.toLocaleString()} detail row${props.loadedRowCount === 1 ? '' : 's'} cached`;
  const loadedSummary = props.focusedScope
    ? 'Focused query updates this view'
    : isRecentRows
    ? `${props.loadedRowCount.toLocaleString()} loaded / ${props.totalAvailableRows.toLocaleString()} total`
    : `${props.totalAvailableRows.toLocaleString()} calls analyzed · ${detailRowLabel}`;
  const loadedSummaryTitle = props.focusedScope
    ? `${props.rowLoadModeLabel} is fetched through the focused endpoint for the current view.`
    : isRecentRows
    ? `${props.loadedRowCount.toLocaleString()} of ${props.totalAvailableRows.toLocaleString()} evidence rows loaded`
    : `Focused pages analyze all ${props.totalAvailableRows.toLocaleString()} calls in scope; ${props.loadedRowCount.toLocaleString()} call rows are cached for immediate detail views.`;
  const accessibleStatus = props.focusedScope
    ? `${props.rowLoadModeLabel} selected; the current view updates through its focused endpoint`
    : isRecentRows
    ? props.rowLoadStatus
    : `${props.rowLoadModeLabel} analysis uses ${props.totalAvailableRows.toLocaleString()} calls; ${detailRowLabel}`;

  return (
    <section className="data-window-control" aria-label="Analysis scope">
      <div className="data-window-summary">
        <span>Analysis scope</span>
        <strong>{props.rowLoadModeLabel}</strong>
        <small title={loadedSummaryTitle}>{loadedSummary}</small>
      </div>
      <div className="data-window-options" role="group" aria-label="Choose loaded call window">
        {windowOptions.map(option => (
          <button
            type="button"
            key={option.value}
            aria-label={option.ariaLabel}
            aria-pressed={props.loadWindow === option.value}
            disabled={disabled}
            onClick={() => props.onWindowChange(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {props.loadWindow === 'rows' ? (
        <div className="row-window-editor">
          <input
            aria-label="Rows to load slider"
            aria-valuetext={`${props.finitePendingLoadLimit.toLocaleString()} recent rows`}
            type="range"
            min={1}
            max={props.rowLimitSliderMax}
            step={100}
            value={props.rowLimitSliderValue}
            onChange={event => props.onSliderChange(event.target.value)}
            disabled={disabled}
          />
          <input
            aria-label="Rows to load"
            type="number"
            min={1}
            step={100}
            value={props.pendingLoadLimit}
            onChange={event => props.onDraftChange(event.target.value)}
            disabled={disabled}
          />
          <button type="button" data-primary="true" onClick={props.onApply} disabled={disabled || !props.rowLimitChanged}>
            {props.loadLabel}
          </button>
          <button type="button" onClick={props.onLoadMore} disabled={disabled || !props.hasMoreRows}>
            {props.loadMoreLabel}
          </button>
        </div>
      ) : null}
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
            {props.refreshProgressPercent === null ? props.refreshProgressText : `${Math.round(props.refreshProgressPercent)}% loaded`}
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
      <span className="sr-only" role="status" aria-live="polite">{accessibleStatus}</span>
    </section>
  );
}
