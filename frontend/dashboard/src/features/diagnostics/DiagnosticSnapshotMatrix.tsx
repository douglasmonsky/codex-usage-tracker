import { Copy, RefreshCw, Search } from 'lucide-react';
import { useMemo, useState } from 'react';

import {
  type DiagnosticSnapshotDefinition,
  type DiagnosticSnapshotKey,
  diagnosticSnapshotDefinitions,
} from '../../api/diagnostics';
import type { ContextRuntime, DashboardModel } from '../../api/types';
import { useShellI18n } from '../../app/i18nContext';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { PageLoadProgress } from '../../design';
import { snapshotCard, type SnapshotCard, type SnapshotRow } from './diagnosticSnapshotCards';
import { fallbackDiagnosticSnapshots } from './diagnosticSnapshotFallbacks';
import { useDiagnosticSnapshots } from './useDiagnosticSnapshots';

type SectionRefreshStatus = 'refreshing' | 'ready' | 'error';

const compactSnapshotRowCount = 4;

export function DiagnosticSnapshotMatrix({
  model,
  contextRuntime,
  includeArchived,
  sourceKey,
  sourceRevision,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  includeArchived: boolean;
  sourceKey?: string;
  sourceRevision: string;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const fallbackSnapshots = useMemo(() => fallbackDiagnosticSnapshots(model), [model]);
  const canUseLiveDiagnostics = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const evidence = useDiagnosticSnapshots({
    canUseLive: canUseLiveDiagnostics,
    contextRuntime,
    includeArchived,
    sourceKey,
    sourceRevision,
  });
  const [refreshingAll, setRefreshingAll] = useState(false);
  const [refreshError, setRefreshError] = useState('');
  const [sectionRefreshStatuses, setSectionRefreshStatuses] = useState<Partial<Record<DiagnosticSnapshotKey, SectionRefreshStatus>>>({});
  const [expandedCards, setExpandedCards] = useState<Partial<Record<DiagnosticSnapshotKey, boolean>>>({});
  const hasLiveSnapshots = Object.keys(evidence.snapshots).length > 0;
  const snapshots = canUseLiveDiagnostics && hasLiveSnapshots ? evidence.snapshots : fallbackSnapshots;
  const statusLabel = snapshotStatusLabel({
    canUseLiveDiagnostics,
    hasLiveSnapshots,
    liveSnapshotCount: Object.keys(evidence.snapshots).length,
    progressError: evidence.progressError,
    refreshingAll,
  });
  const refreshProgress = refreshingAll && evidence.refreshJob
    ? evidence.refreshJob.progress
    : null;
  const progressCompleted = refreshProgress?.completed_units ?? evidence.progress.ready;
  const progressTotal = refreshProgress?.total_units ?? evidence.progress.total;
  const progressLabel = refreshingAll ? 'Refreshing diagnostic snapshots' : 'Loading diagnostic snapshots';
  const progressModules = refreshProgress
    ? evidence.modules.map((module, index) => ({
        ...module,
        status: index < refreshProgress.completed_units ? 'ready' as const : 'updating' as const,
      }))
    : evidence.modules;

  async function refreshSnapshots() {
    if (!canUseLiveDiagnostics || evidence.loading || refreshingAll) return;
    setRefreshingAll(true);
    setRefreshError('');
    try {
      await evidence.refreshAll();
      setSectionRefreshStatuses({});
    } catch (error) {
      setRefreshError(errorMessage(error));
    } finally {
      setRefreshingAll(false);
    }
  }

  async function refreshSnapshot(definition: DiagnosticSnapshotDefinition) {
    if (!canUseLiveDiagnostics || evidence.loading || refreshingAll || sectionRefreshStatuses[definition.key] === 'refreshing') {
      return;
    }
    setRefreshError('');
    setSectionRefreshStatuses(current => ({ ...current, [definition.key]: 'refreshing' }));
    try {
      await evidence.refreshOne(definition);
      setSectionRefreshStatuses(current => ({ ...current, [definition.key]: 'ready' }));
    } catch (error) {
      setRefreshError(`Snapshot refresh failed: ${errorMessage(error)}`);
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
          disabled={!canUseLiveDiagnostics || evidence.loading || refreshingAll}
        >
          <RefreshCw size={15} /> {refreshingAll ? 'Refreshing' : 'Refresh snapshots'}
        </button>
      }
    >
      <PageLoadProgress
        active={canUseLiveDiagnostics && (evidence.loading || refreshingAll)}
        completed={progressCompleted}
        total={progressTotal}
        label={progressLabel}
        error={canUseLiveDiagnostics ? refreshError || evidence.progressError : null}
        modules={progressModules}
        updating={refreshingAll || evidence.modules.some(module => module.status === 'updating')}
      />
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
      {refreshError ? (
        <p className="context-state-note error">Live diagnostic snapshots unavailable: {refreshError}</p>
      ) : null}
    </Panel>
  );
}

function snapshotStatusLabel({
  canUseLiveDiagnostics,
  hasLiveSnapshots,
  liveSnapshotCount,
  progressError,
  refreshingAll,
}: {
  canUseLiveDiagnostics: boolean;
  hasLiveSnapshots: boolean;
  liveSnapshotCount: number;
  progressError: string | null;
  refreshingAll: boolean;
}): string {
  if (refreshingAll) return 'Refreshing diagnostic snapshots...';
  if (hasLiveSnapshots) return `Live snapshots: ${liveSnapshotCount}`;
  if (progressError || !canUseLiveDiagnostics) return 'Static fallback snapshots';
  return 'Loading diagnostic snapshots...';
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
 const i18n = useShellI18n();
 const reloading = refreshStatus === 'refreshing';
 const reloadLabel = reloading ? 'Reloading' : refreshStatus === 'error' ? 'Retry' : 'Reload';
 const visibleRows = expanded ? card.rows : card.rows.slice(0, compactSnapshotRowCount);
 const hiddenRowCount = Math.max(card.rows.length - visibleRows.length, 0);
 const rowListId = `diagnostics-snapshot-${cardKey}-rows`;
 return (
    <article className="diagnostics-snapshot-card">
      <div className="diagnostics-snapshot-card-head">
        <div>
          <h3>{i18n.translateText(card.title)}</h3>
          <p>{i18n.translateText(card.subtitle)}</p>
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
            <small>{i18n.translateText(metric.label)}</small>
            <strong>{i18n.translateText(metric.value)}</strong>
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
