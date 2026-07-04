import { Copy, RefreshCw, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  cachedDiagnosticSnapshots,
  type DiagnosticSnapshotDefinition,
  type DiagnosticSnapshotKey,
  diagnosticSnapshotDefinitions,
  loadDiagnosticSnapshots,
  refreshDiagnosticSnapshot,
  refreshDiagnosticSnapshots,
  type DiagnosticSnapshotMap,
} from '../../api/diagnostics';
import type { ContextRuntime, DashboardModel } from '../../api/types';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { snapshotCard, type SnapshotCard, type SnapshotRow } from './diagnosticSnapshotCards';
import { fallbackDiagnosticSnapshots } from './diagnosticSnapshotFallbacks';

type SnapshotState =
  | { status: 'idle'; message: string; snapshots: DiagnosticSnapshotMap }
  | { status: 'loading'; message: string; snapshots: DiagnosticSnapshotMap }
  | { status: 'loaded'; message: string; snapshots: DiagnosticSnapshotMap }
  | { status: 'error'; message: string; snapshots: DiagnosticSnapshotMap };

type SectionRefreshStatus = 'refreshing' | 'ready' | 'error';

const compactSnapshotRowCount = 4;

export function DiagnosticSnapshotMatrix({
  model,
  contextRuntime,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const fallbackSnapshots = useMemo(() => fallbackDiagnosticSnapshots(model), [model]);
  const canUseLiveDiagnostics = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
 const [snapshotState, setSnapshotState] = useState<SnapshotState>(() => initialSnapshotState(contextRuntime, canUseLiveDiagnostics));
 const [sectionRefreshStatuses, setSectionRefreshStatuses] = useState<Partial<Record<DiagnosticSnapshotKey, SectionRefreshStatus>>>({});
 const [expandedCards, setExpandedCards] = useState<Partial<Record<DiagnosticSnapshotKey, boolean>>>({});
const hasLiveSnapshots = Object.keys(snapshotState.snapshots).length > 0;
const snapshots = canUseLiveDiagnostics && hasLiveSnapshots ? snapshotState.snapshots : fallbackSnapshots;
const statusLabel =
snapshotState.status === 'loaded'
? snapshotState.message
: snapshotState.status === 'error'
? hasLiveSnapshots
? snapshotState.message
: 'Static fallback snapshots'
: canUseLiveDiagnostics
? snapshotState.message
: 'Static fallback snapshots';

  useEffect(() => {
    if (!canUseLiveDiagnostics) {
      setSnapshotState({ status: 'idle', message: 'Static aggregate fallback', snapshots: {} });
      setSectionRefreshStatuses({});
      return;
    }

    const cached = cachedDiagnosticSnapshots(contextRuntime);
    if (cached) {
      setSnapshotState(liveSnapshotState(cached));
      setSectionRefreshStatuses({});
      return;
    }

    let cancelled = false;
    setSnapshotState(current => ({
      status: 'loading',
      message: 'Loading diagnostic snapshots...',
      snapshots: current.snapshots,
    }));
    loadDiagnosticSnapshots(contextRuntime)
      .then(payload => {
        if (!cancelled) {
          setSnapshotState(liveSnapshotState(payload));
          setSectionRefreshStatuses({});
        }
      })
.catch(error => {
if (!cancelled) {
setSnapshotState(current => ({
status: 'error',
message: errorMessage(error),
snapshots: current.snapshots,
}));
}
});

    return () => {
      cancelled = true;
    };
  }, [canUseLiveDiagnostics, contextRuntime]);

  async function refreshSnapshots() {
    if (!canUseLiveDiagnostics || snapshotState.status === 'loading') {
      return;
    }
    setSnapshotState(current => ({
      status: 'loading',
      message: 'Refreshing diagnostic snapshots...',
      snapshots: current.snapshots,
    }));
    try {
      const payload = await refreshDiagnosticSnapshots(contextRuntime);
      setSnapshotState(liveSnapshotState(payload));
      setSectionRefreshStatuses({});
} catch (error) {
setSnapshotState(current => ({
status: 'error',
message: errorMessage(error),
snapshots: current.snapshots,
}));
}
}

  async function refreshSnapshot(definition: DiagnosticSnapshotDefinition) {
    if (!canUseLiveDiagnostics || snapshotState.status === 'loading' || sectionRefreshStatuses[definition.key] === 'refreshing') {
      return;
    }
    setSectionRefreshStatuses(current => ({ ...current, [definition.key]: 'refreshing' }));
    try {
      const payload = await refreshDiagnosticSnapshot(definition, contextRuntime);
      setSnapshotState(current => {
        const snapshots = { ...current.snapshots, [definition.key]: payload };
        return {
          status: 'loaded',
          message: `Live snapshots: ${Object.keys(snapshots).length}`,
          snapshots,
        };
      });
      setSectionRefreshStatuses(current => ({ ...current, [definition.key]: 'ready' }));
    } catch (error) {
      setSnapshotState(current => ({
        status: current.status === 'idle' ? 'error' : current.status,
        message: `Snapshot refresh failed: ${errorMessage(error)}`,
        snapshots: current.snapshots,
      }));
      setSectionRefreshStatuses(current => ({ ...current, [definition.key]: 'error' }));
    }
  }

  return (
    <Panel
      title="Diagnostics Snapshot Matrix"
      subtitle={statusLabel}
      className="span-all"
      action={
        <button
          className="toolbar-button"
          type="button"
          onClick={refreshSnapshots}
          disabled={!canUseLiveDiagnostics || snapshotState.status === 'loading'}
        >
          <RefreshCw size={15} /> {snapshotState.status === 'loading' ? 'Loading' : 'Refresh snapshots'}
        </button>
      }
    >
      <div className="diagnostics-snapshot-grid">
        {diagnosticSnapshotDefinitions.map(definition => (
          <SnapshotCardView
            key={definition.key}
            cardKey={definition.key}
            card={snapshotCard(definition, snapshots[definition.key] ?? fallbackSnapshots[definition.key])}
            canRefresh={canUseLiveDiagnostics}
            refreshStatus={sectionRefreshStatuses[definition.key]}
            expanded={Boolean(expandedCards[definition.key])}
            onExpandedChange={expanded => setExpandedCards(current => ({ ...current, [definition.key]: expanded }))}
            onRefresh={() => refreshSnapshot(definition)}
            onOpenInvestigator={onOpenInvestigator}
            onCopyCallLink={onCopyCallLink}
            />
        ))}
      </div>
      {snapshotState.status === 'error' ? (
        <p className="context-state-note error">Live diagnostic snapshots unavailable: {snapshotState.message}</p>
      ) : null}
    </Panel>
  );
}

function initialSnapshotState(contextRuntime: ContextRuntime, canUseLiveDiagnostics: boolean): SnapshotState {
  if (!canUseLiveDiagnostics) return staticSnapshotState();
  const cached = cachedDiagnosticSnapshots(contextRuntime);
  return cached ? liveSnapshotState(cached) : staticSnapshotState();
}

function staticSnapshotState(): SnapshotState {
  return { status: 'idle', message: 'Static aggregate fallback', snapshots: {} };
}

function liveSnapshotState(snapshots: DiagnosticSnapshotMap): SnapshotState {
  return {
    status: 'loaded',
    message: `Live snapshots: ${Object.keys(snapshots).length}`,
    snapshots,
  };
}

function SnapshotCardView({
 cardKey,
 card,
 canRefresh,
 refreshStatus,
 expanded,
 onExpandedChange,
 onRefresh,
 onOpenInvestigator,
 onCopyCallLink,
}: {
 cardKey: DiagnosticSnapshotKey;
 card: SnapshotCard;
 canRefresh: boolean;
 refreshStatus?: SectionRefreshStatus;
 expanded: boolean;
 onExpandedChange: (expanded: boolean) => void;
 onRefresh: () => void;
 onOpenInvestigator: (recordId: string) => void;
 onCopyCallLink: (recordId: string) => void;
}) {
 const reloading = refreshStatus === 'refreshing';
 const reloadLabel = reloading ? 'Reloading' : refreshStatus === 'error' ? 'Retry' : 'Reload';
 const visibleRows = expanded ? card.rows : card.rows.slice(0, compactSnapshotRowCount);
 const hiddenRowCount = Math.max(card.rows.length - visibleRows.length, 0);
 const rowListId = `diagnostics-snapshot-${cardKey}-rows`;
 return (
    <article className="diagnostics-snapshot-card">
      <div className="diagnostics-snapshot-card-head">
        <div>
          <h3>{card.title}</h3>
          <p>{card.subtitle}</p>
        </div>
        <div className="diagnostics-snapshot-card-actions">
          <StatusBadge label={card.status} tone={card.status === 'ready' ? 'green' : card.status === 'fallback' ? 'blue' : 'orange'} />
          {canRefresh ? (
            <button
              className="toolbar-button diagnostics-section-refresh"
              type="button"
              aria-label={`Reload ${card.title} diagnostic snapshot`}
              onClick={onRefresh}
              disabled={reloading}
            >
              <RefreshCw size={13} /> {reloadLabel}
            </button>
          ) : null}
        </div>
      </div>
      <div className="diagnostics-snapshot-metrics">
        {card.metrics.map(metric => (
          <span key={`${card.title}-${metric.label}`}>
            <small>{metric.label}</small>
            <strong>{metric.value}</strong>
          </span>
        ))}
      </div>
      <ol className="diagnostics-snapshot-rows" id={rowListId}>
        {card.rows.length ? (
          visibleRows.map(row => (
            <li key={`${card.title}-${row.label}-${row.value}`} className={row.recordId ? 'has-row-action' : undefined}>
              {row.recordId ? (
                <>
                  <button
                    className="diagnostics-snapshot-row-button"
                    type="button"
                    aria-label={`Open investigator for diagnostic snapshot ${card.title} ${row.label}`}
                    onClick={() => onOpenInvestigator(String(row.recordId))}
                  >
                    <span>
                      <strong>{row.label}</strong>
                      <em>{row.detail}</em>
                    </span>
                    <b>{row.value}</b>
                    <span className="diagnostics-snapshot-row-open">
                      <Search size={14} /> Open
                    </span>
                  </button>
                  <button
                    className="diagnostics-snapshot-row-copy"
                    type="button"
                    aria-label={`Copy link for diagnostic snapshot ${card.title} ${row.label}`}
                    onClick={() => onCopyCallLink(String(row.recordId))}
                  >
                      <Copy size={14} /> Copy
                    </button>
                    <SnapshotRowChildren row={row} />
                  </>
                ) : (
                  <>
                    <span>
                      <strong>{row.label}</strong>
                      <em>{row.detail}</em>
                    </span>
                    <b>{row.value}</b>
                    <SnapshotRowChildren row={row} />
                  </>
                )}
              </li>
          ))
        ) : (
          <li className="empty-state">No aggregate rows in this snapshot.</li>
        )}
      </ol>
      {card.rows.length > compactSnapshotRowCount ? (
        <div className="diagnostics-snapshot-row-depth">
          <span>
            {expanded
              ? `Showing all ${card.rows.length.toLocaleString()} rows`
              : `Showing ${visibleRows.length.toLocaleString()} of ${card.rows.length.toLocaleString()} rows`}
          </span>
          <button
            className="inline-button"
            type="button"
            aria-controls={rowListId}
            aria-expanded={expanded}
            onClick={() => onExpandedChange(!expanded)}
          >
            {expanded ? 'Show fewer' : `Show ${hiddenRowCount.toLocaleString()} more`}
          </button>
        </div>
      ) : null}
    </article>
  );
}

function SnapshotRowChildren({ row }: { row: SnapshotRow }) {
  if (!row.children?.length) return null;
  const childCount = row.children.length;
  return (
    <details className="diagnostics-snapshot-row-children">
      <summary>
        {`Show ${childCount.toLocaleString()} child ${childCount === 1 ? 'command' : 'commands'}`}
      </summary>
      <ul>
        {row.children.map(child => (
          <li key={`${row.label}-${child.label}-${child.value}`}>
            <span>{child.label}</span>
            <b>{child.value}</b>
          </li>
        ))}
      </ul>
    </details>
  );
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
