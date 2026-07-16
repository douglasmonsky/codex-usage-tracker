import type { Table } from '@tanstack/react-table';
import { useEffect, useRef, useState } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import type { EvidenceGridDensity } from './useEvidenceGridPreferences';
import styles from './EvidenceGrid.module.css';

export type EvidenceGridControlsProps<TData> = {
  ariaLabel: string;
  table: Table<TData>;
  lockedColumnIds: ReadonlySet<string>;
  density: EvidenceGridDensity;
  onDensityChange(density: EvidenceGridDensity): void;
  onRestoreDefaults(): void;
};

function headerText(header: unknown, fallback: string): string {
  return typeof header === 'string' ? header : fallback;
}

export function EvidenceGridControls<TData>({
  ariaLabel,
  table,
  lockedColumnIds,
  density,
  onDensityChange,
  onRestoreDefaults,
}: EvidenceGridControlsProps<TData>) {
  const i18n = useShellI18n();
  const chooserRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    const close = (event: KeyboardEvent | PointerEvent) => {
      if (event instanceof KeyboardEvent && event.key === 'Escape') {
        setOpen(false);
        return;
      }
      if (event instanceof PointerEvent && !chooserRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', close);
    document.addEventListener('pointerdown', close);
    return () => {
      document.removeEventListener('keydown', close);
      document.removeEventListener('pointerdown', close);
    };
  }, [open]);

  return <div className={styles.toolbar} aria-label={i18n.translateText(`${ariaLabel} display controls`)}>
    <div className={styles.densityControl} role="group" aria-label="Density">
      <button type="button" aria-pressed={density === 'compact'} onClick={() => onDensityChange('compact')}>Dense</button>
      <button type="button" aria-pressed={density === 'comfortable'} onClick={() => onDensityChange('comfortable')}>Roomy</button>
    </div>
    <div className={styles.columnChooser} ref={chooserRef}>
      <button type="button" aria-expanded={open} onClick={() => setOpen(current => !current)}>Columns</button>
      {open ? <fieldset>
        <legend>Visible columns</legend>
        {table.getAllLeafColumns().map(column => {
          const locked = lockedColumnIds.has(column.id);
          return <label key={column.id}>
            <input
              type="checkbox"
              checked={locked || column.getIsVisible()}
              disabled={locked}
              onChange={column.getToggleVisibilityHandler()}
            />
            {i18n.translateText(headerText(column.columnDef.header, column.id))}
          </label>;
        })}
      </fieldset> : null}
    </div>
    <button type="button" className={styles.restoreButton} onClick={onRestoreDefaults}>Restore defaults</button>
  </div>;
}
