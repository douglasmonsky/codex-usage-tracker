import type { VisibilityState } from '@tanstack/react-table';
import { Columns3 } from 'lucide-react';
import { useEffect, useRef } from 'react';

export type ColumnChoice = {
  id: string;
  label: string;
  locked?: boolean;
};

type ColumnChooserProps = {
  label: string;
  columns: ColumnChoice[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  visibility: VisibilityState;
  onVisibilityChange: (visibility: VisibilityState) => void;
};

export function ColumnChooser({ label, columns, open, onOpenChange, visibility, onVisibilityChange }: ColumnChooserProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const visibleCount = columns.filter(column => column.locked || visibility[column.id] !== false).length;

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        onOpenChange(false);
      }
    }
    function handlePointerDown(event: PointerEvent) {
      if (event.target instanceof Node && !menuRef.current?.contains(event.target)) {
        onOpenChange(false);
      }
    }
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('pointerdown', handlePointerDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('pointerdown', handlePointerDown);
    };
  }, [onOpenChange, open]);

  function setColumnVisible(column: ColumnChoice, visible: boolean) {
    if (column.locked) {
      return;
    }
    onVisibilityChange({ ...visibility, [column.id]: visible });
  }

  function showAll() {
    const nextVisibility: VisibilityState = {};
    for (const column of columns) {
      if (!column.locked) {
        nextVisibility[column.id] = true;
      }
    }
    onVisibilityChange(nextVisibility);
  }

  return (
    <div className="column-menu-wrap" ref={menuRef}>
      <button
        className="toolbar-button"
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={`${label}-column-menu`}
        onClick={() => onOpenChange(!open)}
      >
        <Columns3 size={16} />
        Columns
        <span className="toolbar-count">{visibleCount}</span>
      </button>
      {open ? (
        <div className="column-menu" id={`${label}-column-menu`} role="menu">
          <div className="column-menu-head">
            <strong>{label} columns</strong>
            <button type="button" onClick={showAll}>
              Show all
            </button>
          </div>
          <div className="column-menu-options">
            {columns.map(column => (
              <label key={column.id} className={column.locked ? 'locked' : ''}>
                <input
                  type="checkbox"
                  checked={column.locked || visibility[column.id] !== false}
                  disabled={column.locked}
                  onChange={event => setColumnVisible(column, event.target.checked)}
                />
                <span>{column.label}</span>
              </label>
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}
