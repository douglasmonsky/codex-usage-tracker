import { X } from 'lucide-react';
import { useState } from 'react';

import { Button, IconButton, ProgressBar } from '../index';
import styles from './DataScope.module.css';
import type { LabDataState } from './visualContractData';

type DataScopePopoverProps = {
  currentHistory: 'active' | 'all';
  currentRows: number | null;
  dataState: LabDataState;
  refreshing: boolean;
  onApply: (rows: number | null, history: 'active' | 'all') => void;
  onCancelRefresh: () => void;
  onClose: () => void;
  onPreviewStateChange: (state: LabDataState) => void;
  onRefresh: () => void;
};

export function DataScopePopover({
  currentHistory,
  currentRows,
  dataState,
  refreshing,
  onApply,
  onCancelRefresh,
  onClose,
  onPreviewStateChange,
  onRefresh,
}: DataScopePopoverProps) {
  const [history, setHistory] = useState<'active' | 'all'>(currentHistory);
  const [rows, setRows] = useState(String(currentRows ?? 5000));
  const [uncapped, setUncapped] = useState(currentRows === null);

  const apply = () => {
    const parsedRows = Math.max(1, Math.round(Number(rows) || 5000));
    onApply(uncapped ? null : parsedRows, history);
  };

  const finiteRows = Math.max(500, Math.min(20_000, Math.round(Number(rows) || 5000)));

  return (
    <section className={styles.popover} role="dialog" aria-modal="true" aria-labelledby="data-scope-title">
      <div className={styles.header}>
        <div>
          <h2 id="data-scope-title">Data scope</h2>
          <p>Control how much indexed history this workspace loads.</p>
        </div>
        <IconButton aria-label="Close data scope" onClick={onClose}>
          <X />
        </IconButton>
      </div>

      <div className={styles.grid}>
        <label>
          History
          <select value={history} onChange={(event) => setHistory(event.target.value as 'active' | 'all')}>
            <option value="active">Active sessions</option>
            <option value="all">All history</option>
          </select>
        </label>
        <label>
          Rows
          <input
            inputMode="numeric"
            min="1"
            type="number"
            value={rows}
            disabled={uncapped}
            onChange={(event) => setRows(event.target.value)}
          />
        </label>
      </div>

      <label className={styles.rangeLabel}>
        <span><strong>Quick range</strong><span>No fixed maximum</span></span>
        <input
          aria-label="Quick row range"
          disabled={uncapped}
          max="20000"
          min="500"
          step="500"
          type="range"
          value={finiteRows}
          onChange={(event) => setRows(event.target.value)}
        />
      </label>

      <label className={styles.checkboxLabel}>
        <input type="checkbox" checked={uncapped} onChange={(event) => setUncapped(event.target.checked)} /> No row cap
      </label>

      <label className={styles.previewLabel}>
        Preview state
        <select value={dataState} onChange={(event) => onPreviewStateChange(event.target.value as LabDataState)}>
          <option value="ready">Ready</option>
          <option value="loading">Loading</option>
          <option value="empty">Empty</option>
          <option value="stale">Stale while refreshing</option>
          <option value="partial">Partial evidence</option>
          <option value="error">Source error</option>
        </select>
      </label>

      <div className={styles.progress} aria-live="polite">
        <div className={styles.progressLabel}>
          <span>{refreshing ? '7/8 files / 28,419 records / 4.2s' : 'Index current / source revision 184'}</span>
          <strong>{refreshing ? '68%' : '42,318 records'}</strong>
        </div>
        <ProgressBar label="Index refresh" value={refreshing ? 68 : 100} showValue={false} />
      </div>

      <div className={styles.footer}>
        <Button variant="ghost" onClick={refreshing ? onCancelRefresh : onRefresh}>{refreshing ? 'Cancel refresh' : 'Refresh index'}</Button>
        <Button disabled={uncapped} onClick={() => onApply(Math.max(1, Math.round(Number(rows) || 5000)) + 5000, history)}>Load 5,000 more</Button>
        <Button variant="primary" onClick={apply}>{refreshing ? 'Apply after refresh' : 'Apply scope'}</Button>
      </div>
    </section>
  );
}
