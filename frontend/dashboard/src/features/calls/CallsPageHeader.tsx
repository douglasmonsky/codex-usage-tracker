import { Copy, Download, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';
import styles from './CallsPage.module.css';

type CallsPageHeaderProps = {
  workspaceSwitcher?: ReactNode;
  canExport: boolean;
  onExport(): void;
  onCopyView(): void;
  onRefresh(): void;
};

export function CallsPageHeader({
  workspaceSwitcher,
  canExport,
  onExport,
  onCopyView,
  onRefresh,
}: CallsPageHeaderProps) {
  return (
    <header className={styles.pageHeader}>
      <div>
        <p className={styles.eyebrow}>Evidence explorer</p>
        <h1>Calls</h1>
        <p>Find expensive, cold, or context-heavy calls and move directly into their evidence.</p>
      </div>
      <div className={styles.headerActions}>
        {workspaceSwitcher}
        <button className="toolbar-button" type="button" onClick={onExport} disabled={!canExport}>
          <Download size={16} />
          Export
        </button>
        <button className="toolbar-button" type="button" onClick={onCopyView}>
          <Copy size={16} />
          Copy view
        </button>
        <button className="primary-button" type="button" onClick={onRefresh}>
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>
    </header>
  );
}
