import { useVirtualizer } from '@tanstack/react-virtual';
import { ArrowUpRight, Copy, Download } from 'lucide-react';
import { useMemo, useRef, useState, type ReactNode } from 'react';

import type { CallRow } from '../../api/types';
import { useShellI18n } from '../../app/i18nContext';
import { Button, IconButton, StatusBadge, Surface } from '../../design';
import { csvDateStamp, downloadCsv, rowsToCsv } from '../shared/exportCsv';
import { formatCompact, formatNumber, pct } from '../shared/format';
import { callCsvColumns } from '../shared/tables';
import { overviewCallsForQuery } from './overviewCalls';
import styles from './OverviewRecentCalls.module.css';

type OverviewRecentCallsProps = {
  calls: CallRow[];
  globalFilters?: ReactNode;
  globalQuery: string;
  loadedRowCount: number;
  totalAvailableRows: number;
  refreshing: boolean;
  canLoadMoreRows: boolean;
  onLoadMoreRows: () => void;
  onBrowseCalls: () => void;
  onOpenCall: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

export function OverviewRecentCalls(props: OverviewRecentCallsProps) {
  const [exportStatus, setExportStatus] = useState('');
  const shellI18n = useShellI18n();
  const copyLinkLabel = shellI18n.t('button.copy_link', 'Copy link');
  const loadMoreLabel = shellI18n.t('button.load_more', 'Load more');
  const openInvestigatorLabel = shellI18n.t('button.open_investigator', 'Open investigator');
  const visibleCalls = useMemo(
    () => overviewCallsForQuery(props.calls, props.globalQuery),
    [props.calls, props.globalQuery],
  );
  const scrollRef = useRef<HTMLDivElement>(null);
  const virtualizer = useVirtualizer({
    count: visibleCalls.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 58,
    overscan: 8,
    initialRect: { width: 900, height: 348 },
  });
  const virtualRows = virtualizer.getVirtualItems();
  const renderedRows = virtualRows.length
    ? virtualRows
    : visibleCalls.slice(0, 12).map((_, index) => ({ index, start: index * 58 }));

  function exportCalls() {
    downloadCsv(`codex-overview-calls-${csvDateStamp()}.csv`, rowsToCsv(visibleCalls, callCsvColumns));
    setExportStatus(`Exported ${formatNumber(visibleCalls.length)} loaded calls`);
  }

  return (
    <section className={styles.section} aria-labelledby="overview-recent-calls-title">
      <div className={styles.header}>
        <div>
          <h2 id="overview-recent-calls-title">Recent calls</h2>
          <p>{formatNumber(visibleCalls.length)} matching loaded calls. Rows open Call Investigator.</p>
        </div>
        <div className={styles.actions}>
          {exportStatus ? <StatusBadge tone="positive" role="status">{exportStatus}</StatusBadge> : null}
          <Button onClick={exportCalls} disabled={!visibleCalls.length}><Download /> Export</Button>
        </div>
      </div>
      {props.globalFilters}
      <Surface className={styles.tableSurface}>
        <div
          ref={scrollRef}
          className={styles.scroller}
          role="table"
          aria-label="Recent calls"
          aria-rowcount={visibleCalls.length + 1}
        >
          <div className={styles.tableInner} style={{ height: virtualizer.getTotalSize() + 42 }}>
            <div className={styles.tableHeader} role="row">
              <span className={styles.stickyCell} role="columnheader">Thread</span>
              <span role="columnheader">Model / effort</span>
              <span role="columnheader">Tokens</span>
              <span role="columnheader">Cache</span>
              <span role="columnheader">Time</span>
              <span role="columnheader">Actions</span>
            </div>
            {renderedRows.map(virtualRow => {
              const call = visibleCalls[virtualRow.index];
              return (
                <div
                  className={styles.tableRow}
                  data-index={virtualRow.index}
                  key={call.id}
                  role="row"
                  tabIndex={0}
                  aria-label={`Open Call Investigator for ${call.thread}`}
                  style={{ transform: `translateY(${virtualRow.start + 42}px)` }}
                  onClick={() => props.onOpenCall(call.id)}
                  onKeyDown={event => {
                    if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
                      event.preventDefault();
                      props.onOpenCall(call.id);
                    }
                  }}
                >
                  <span className={styles.stickyCell} role="cell"><strong>{call.thread}</strong><small>{call.signal || 'aggregate'}</small></span>
                  <span role="cell"><strong>{call.model}</strong><small>{call.effort || 'unspecified'}</small></span>
                  <span role="cell" className={styles.numeric}>{formatCompact(call.totalTokens)}</span>
                  <span role="cell" className={styles.numeric}>{pct(call.cachedPct)}</span>
                  <span role="cell">{call.time}</span>
                  <span className={styles.rowActions} role="cell">
                    <IconButton aria-label={`${openInvestigatorLabel} for ${call.thread} ${call.model}`} title={openInvestigatorLabel} onClick={event => { event.stopPropagation(); props.onOpenCall(call.id); }}><ArrowUpRight /></IconButton>
                    <IconButton aria-label={`${copyLinkLabel} for ${call.thread} ${call.model}`} title={copyLinkLabel} onClick={event => { event.stopPropagation(); props.onCopyCallLink(call.id); }}><Copy /></IconButton>
                  </span>
                </div>
              );
            })}
          </div>
        </div>
        {!visibleCalls.length ? <p className={styles.empty}>No loaded calls match the current search.</p> : null}
        <footer className={styles.footer}>
          <span>Loaded {formatNumber(props.loadedRowCount)} of {formatNumber(props.totalAvailableRows)} available calls</span>
          <div className={styles.actions}>
            <Button aria-label="Load more recent calls" onClick={props.onLoadMoreRows} disabled={!props.canLoadMoreRows || props.refreshing}>{props.refreshing ? 'Loading...' : loadMoreLabel}</Button>
            <Button onClick={props.onBrowseCalls}>Browse all calls</Button>
          </div>
        </footer>
      </Surface>
    </section>
  );
}
