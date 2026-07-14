import { Copy, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import type {
  DiagnosticFactCallsResult,
  DiagnosticFactRow,
  DiagnosticFactSourceKey,
} from '../../api/diagnostics';
import type { CallRow } from '../../api/types';
import { Panel } from '../../components/Panel';
import { formatCompact, formatNumber, pct } from '../shared/format';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';
import { diagnosticFactKey, factCallsHasMore, factCallsTotal } from './diagnosticFactCalls';
import type { FactCallsState, FactLoadState, FactSourcePanelState } from './diagnosticFactStates';
import {
cachePctFromFact,
defaultFactCallSortDirection,
defaultFactSortDirection,
  diagnosticFactCallSortDescription,
  diagnosticFactSortDescription,
  factCallSortOptions,
  factSortOptions,
  numberField,
  sortDiagnosticFactCalls,
  sortDiagnosticFacts,
  type FactCallSortKey,
  type FactCallSortState,
  type FactSortKey,
  type FactSortState,
} from './diagnosticFactSorting';

const FACT_PREVIEW_COUNT = 6;
const FACT_VISIBLE_COUNT_STORAGE_KEY = 'codexUsageDiagnosticsFactVisibleCounts';

export type { FactCallsState, FactLoadState, FactSourcePanelState } from './diagnosticFactStates';

export type DashboardRowLoadControls = {
  loadedRowCount: number;
  totalAvailableRows: number;
  canLoadMoreRows: boolean;
  canLoadAllRows: boolean;
  refreshing: boolean;
  onLoadMoreRows: () => void;
  onLoadAllRows: () => void;
};

export function StructuredFactsPanel({
  sources,
  activeSourceKey,
  facts,
  selectedFact,
  factState,
  factSort,
  onFactSortChange,
  onSelectSource,
  onSelectFact,
  canLoadMoreFacts,
  loadingMoreFacts,
  onLoadMoreFacts,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  sources: FactSourcePanelState[];
  activeSourceKey: DiagnosticFactSourceKey;
  facts: DiagnosticFactRow[];
  selectedFact: DiagnosticFactRow | null;
  factState: FactLoadState;
  factSort: FactSortState;
  onFactSortChange: (sort: FactSortState) => void;
  onSelectSource: (key: DiagnosticFactSourceKey) => void;
  onSelectFact: (fact: DiagnosticFactRow) => void;
  canLoadMoreFacts: boolean;
  loadingMoreFacts: boolean;
  onLoadMoreFacts: () => void;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const [visibleFactCount, setVisibleFactCount] = useState(() =>
    readFactVisibleCount(activeSourceKey, factSort),
  );
  const activeSource = sources.find(source => source.key === activeSourceKey);
  const sourceTitle = activeSource?.title ?? 'Structured Diagnostic Facts';
  const sortedFacts = useMemo(() => sortDiagnosticFacts(facts, factSort.key, factSort.direction), [facts, factSort]);
  const visibleFacts = sortedFacts.slice(0, visibleFactCount);
  const hiddenFactCount = Math.max(facts.length - visibleFacts.length, 0);
  const loadedFactCount = facts.length;
  const matchedFactCount =
    factState.status === 'loaded'
      ? Math.max(numberField(factState.payload.total_matched_rows), loadedFactCount)
      : loadedFactCount;
  const factCountSummary =
    matchedFactCount > loadedFactCount
      ? `${formatNumber(loadedFactCount)} loaded / ${formatNumber(matchedFactCount)} matched`
      : `${formatNumber(loadedFactCount)} matched`;
  const sortDescription = diagnosticFactSortDescription(factSort);
  const subtitle =
    factState.status === 'error'
      ? `Live ${sourceTitle.toLowerCase()} unavailable: ${factState.message}`
      : factState.status === 'loading'
        ? factState.message
        : `${sourceTitle} module - ${factCountSummary} - ${sortDescription}`;

  useEffect(() => {
    setVisibleFactCount(readFactVisibleCount(activeSourceKey, factSort));
  }, [activeSourceKey, factSort]);

  useEffect(() => {
    if (visibleFacts.length && !visibleFacts.some(fact => selectedFact && diagnosticFactKey(fact) === diagnosticFactKey(selectedFact))) {
      onSelectFact(visibleFacts[0]);
    }
  }, [onSelectFact, selectedFact, visibleFacts]);

  return (
    <Panel title="Structured Diagnostic Facts" subtitle={subtitle}>
      <div className="drilldown-tabs diagnostic-source-tabs" role="tablist" aria-label="Diagnostic fact modules">
        {sources.map(source => (
          <button
            key={source.key}
            type="button"
            role="tab"
            aria-selected={source.key === activeSourceKey}
            className={source.key === activeSourceKey ? 'active' : ''}
            onClick={() => onSelectSource(source.key)}
          >
            <span>{source.label}</span>
            <small>{sourceStatusLabel(source.state)}</small>
          </button>
        ))}
      </div>

      <div className="diagnostic-fact-controls">
        <label className="mini-select-field">
          Sort facts
          <select
              aria-label="Sort diagnostic facts"
              value={factSort.key}
              onChange={event => {
                const key = event.target.value as FactSortKey;
                onFactSortChange({ key, direction: defaultFactSortDirection(key) });
              }}
            >
            {factSortOptions.map(option => (
              <option key={option.key} value={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="pager-button"
          type="button"
          aria-label={`Sort diagnostic facts ${factSort.direction === 'desc' ? 'ascending' : 'descending'}`}
          onClick={() => onFactSortChange({ ...factSort, direction: factSort.direction === 'desc' ? 'asc' : 'desc' })}
        >
          {factSort.direction === 'desc' ? 'Descending' : 'Ascending'}
        </button>
      </div>

      <div className="diagnostic-fact-list">
        {facts.length ? (
          visibleFacts.map(fact => {
            const selected = selectedFact ? diagnosticFactKey(fact) === diagnosticFactKey(selectedFact) : false;
            return (
              <article
                key={diagnosticFactKey(fact)}
                className={selected ? 'diagnostic-fact-card active' : 'diagnostic-fact-card'}
              >
                <button className="diagnostic-fact-select" type="button" onClick={() => onSelectFact(fact)}>
                  <span>
                    {fact.fact_type || 'fact'} / {fact.fact_name || 'unknown'}
                  </span>
                  <strong>{formatCompact(numberField(fact.associated_uncached_input_tokens))} uncached</strong>
                  <small>
                    {formatNumber(numberField(fact.associated_calls))} calls - {pct(cachePctFromFact(fact))} cache
                  </small>
                </button>
                <div className="diagnostic-fact-meta">
                  <span>
                    <b>Category</b>
                    {fact.fact_category || 'uncategorized'}
                  </span>
                  <span>
                    <b>Occurrences</b>
                    {formatNumber(numberField(fact.occurrences))}
                  </span>
                  <span>
                    <b>Total</b>
                    {formatCompact(numberField(fact.associated_total_tokens))}
                  </span>
                  <span>
                    <b>Input</b>
                    {formatCompact(numberField(fact.associated_input_tokens))}
                  </span>
                  <span>
                    <b>Cached</b>
                    {formatCompact(numberField(fact.associated_cached_input_tokens))}
                  </span>
                  <span>
                    <b>Output</b>
                    {formatCompact(numberField(fact.associated_output_tokens))}
                  </span>
                  <span>
                    <b>Reasoning</b>
                    {formatCompact(numberField(fact.associated_reasoning_output_tokens))}
                  </span>
                  <span>
                    <b>Largest</b>
                    {formatCompact(numberField(fact.largest_call_tokens))}
                  </span>
                  <span>
                    <b>Latest</b>
                    {formatFactTime(fact.latest_event_timestamp)}
                  </span>
                </div>
                    {fact.largest_record_id ? (
                      <div className="table-action-group">
                        <button
                          className="table-action-button"
                          type="button"
                          aria-label={`Open investigator largest diagnostic fact call ${fact.fact_type} ${fact.fact_name}`}
                          onClick={() => onOpenInvestigator(String(fact.largest_record_id))}
                        >
                          <Search size={14} /> Largest
                        </button>
                        <button
                          className="table-action-button"
                          type="button"
                          aria-label={`Copy link for largest diagnostic fact call ${fact.fact_type} ${fact.fact_name}`}
                          onClick={() => onCopyCallLink(String(fact.largest_record_id))}
                        >
                          <Copy size={14} /> Copy
                        </button>
                      </div>
                    ) : null}
              </article>
            );
          })
        ) : (
          <p className="empty-state">No diagnostic facts matched the current aggregate data.</p>
        )}
      </div>
      {facts.length > FACT_PREVIEW_COUNT || canLoadMoreFacts ? (
        <div className="child-load-more diagnostics-fact-load-more">
          <span>
          Showing {formatNumber(visibleFacts.length)} of {formatNumber(loadedFactCount)} loaded facts
          {matchedFactCount > loadedFactCount ? ` / ${formatNumber(matchedFactCount)} matched` : ''}
          </span>
          {hiddenFactCount ? (
            <button
              className="pager-button"
              type="button"
              onClick={() =>
                setVisibleFactCount(count => {
                  const nextCount = Math.min(count + FACT_PREVIEW_COUNT, facts.length);
                  rememberFactVisibleCount(activeSourceKey, factSort, nextCount);
                  return nextCount;
                })
              }
            >
              Show {formatNumber(Math.min(FACT_PREVIEW_COUNT, hiddenFactCount))} more
            </button>
          ) : null}
          {canLoadMoreFacts ? (
            <button className="pager-button" type="button" onClick={onLoadMoreFacts} disabled={loadingMoreFacts}>
              {loadingMoreFacts ? 'Loading more facts...' : 'Load more live facts'}
            </button>
          ) : null}
        </div>
      ) : null}
    </Panel>
  );
}

export function FactCallsPanel({
  selectedFact,
  calls,
  status,
  usingLiveFacts,
  liveResult,
  factCallSort,
  rowLoadControls,
  onFactCallSortChange,
  onLoadMore,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  selectedFact: DiagnosticFactRow | null;
  calls: CallRow[];
  status: FactCallsState;
  usingLiveFacts: boolean;
  liveResult: DiagnosticFactCallsResult | null;
  factCallSort: FactCallSortState;
  rowLoadControls: DashboardRowLoadControls;
  onFactCallSortChange: (sort: FactCallSortState) => void;
  onLoadMore: () => void;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const label = selectedFact ? `${selectedFact.fact_type || 'fact'} / ${selectedFact.fact_name || 'unknown'}` : 'No fact selected';
  const liveTotal = liveResult ? factCallsTotal(liveResult) : calls.length;
  const canLoadMore = usingLiveFacts && liveResult ? factCallsHasMore(liveResult) : false;
  const loadingMore = status.status === 'appending';
  const showDashboardRowControls =
    rowLoadControls.canLoadMoreRows || rowLoadControls.canLoadAllRows || rowLoadControls.totalAvailableRows > rowLoadControls.loadedRowCount;
  const sortedCalls = useMemo(() => sortDiagnosticFactCalls(calls, factCallSort.key, factCallSort.direction), [calls, factCallSort]);
  const sortDescription = diagnosticFactCallSortDescription(factCallSort);
  const subtitle =
    status.status === 'loading'
      ? status.message
      : status.status === 'error'
        ? `Live calls unavailable: ${status.message}`
        : usingLiveFacts
          ? `${formatNumber(calls.length)} of ${formatNumber(liveTotal)} live fact calls`
          : `${calls.length} fallback aggregate calls`;

  return (
    <Panel title="Diagnostic Fact Calls" subtitle={subtitle}>
      <div className="section-heading compact">
        <h3>{label}</h3>
        <span>
          {calls.length
            ? `Showing ${formatNumber(calls.length)} of ${formatNumber(liveTotal)} calls - ${sortDescription}`
            : 'No loaded rows'}
        </span>
      </div>

      {calls.length ? (
        <>
          <div className="diagnostic-fact-controls diagnostic-call-controls">
            <label className="mini-select-field">
              Sort calls
            <select
              aria-label="Sort diagnostic fact calls"
              value={factCallSort.key}
              onChange={event => {
                const key = event.target.value as FactCallSortKey;
                onFactCallSortChange({ key, direction: defaultFactCallSortDirection(key) });
              }}
            >
                {factCallSortOptions.map(option => (
                  <option key={option.key} value={option.key}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <button
          className="pager-button"
          type="button"
          aria-label={`Sort diagnostic fact calls ${factCallSort.direction === 'desc' ? 'ascending' : 'descending'}`}
          onClick={() => onFactCallSortChange({ ...factCallSort, direction: factCallSort.direction === 'desc' ? 'asc' : 'desc' })}
        >
          {factCallSort.direction === 'desc' ? 'Descending' : 'Ascending'}
        </button>
          </div>
          <div className="table-scroll diagnostic-fact-call-scroll">
            <table className="data-table compact diagnostic-fact-call-table" aria-label="Diagnostic fact calls">
              <thead>
                <tr>
                  <th>Time</th>
<th className="sticky-column">Thread</th>
                  <th>Model</th>
                  <th>Effort</th>
                  <th className="numeric">Input</th>
                  <th className="numeric">Total</th>
                  <th className="numeric">Cached</th>
                  <th className="numeric">Uncached</th>
                  <th className="numeric">Output</th>
                  <th className="numeric">Reasoning</th>
                  <th className="numeric">Cache %</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {sortedCalls.map(call => (
                  <tr
                    key={`${label}-${call.id}`}
                    className="is-clickable is-activatable"
                    tabIndex={0}
                    aria-label={`Open investigator diagnostic fact call ${call.thread} ${call.model}`}
                    onClick={() => onOpenInvestigator(call.id)}
                    onKeyDown={event => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault();
                        onOpenInvestigator(call.id);
                      }
                    }}
                  >
                    <td>{call.time}</td>
<td className="sticky-column">
<strong>{call.thread}</strong>
</td>
                    <td>{call.model}</td>
                    <td>{call.effort}</td>
                    <td className="numeric">{formatCompact(call.input)}</td>
                    <td className="numeric">{formatCompact(call.totalTokens)}</td>
                    <td className="numeric">{formatCompact(call.cachedInput)}</td>
                    <td className="numeric">{formatCompact(call.uncachedInput)}</td>
                    <td className="numeric">{formatCompact(call.output)}</td>
                    <td className="numeric">{formatCompact(call.reasoningOutput)}</td>
                    <td className="numeric">{pct(call.cachedPct)}</td>
                    <td>
                      <div className="table-action-group">
                        <button
                          className="table-action-button"
                          type="button"
                          aria-label={`Open investigator diagnostic fact call ${call.thread} ${call.model}`}
 onKeyDown={stopRowActionKeyDown}
                          onClick={event => {
                            event.stopPropagation();
                            onOpenInvestigator(call.id);
                          }}
                        >
                          <Search size={14} /> Open
                        </button>
                        <button
                          className="table-action-button"
                          type="button"
                          aria-label={`Copy link for diagnostic fact call ${call.thread} ${call.model}`}
 onKeyDown={stopRowActionKeyDown}
                          onClick={event => {
                            event.stopPropagation();
                            onCopyCallLink(call.id);
                          }}
                        >
                          <Copy size={14} /> Copy
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {usingLiveFacts || showDashboardRowControls ? (
            <div className="child-load-more diagnostics-call-load-more">
              <div>
                <span>
                  Showing {formatNumber(calls.length)} of {formatNumber(liveTotal)} calls
                </span>
                {showDashboardRowControls ? (
                  <small>
                    Dashboard rows: {formatNumber(rowLoadControls.loadedRowCount)} of {formatNumber(rowLoadControls.totalAvailableRows)} loaded
                  </small>
                ) : null}
              </div>
              <div className="panel-action-group">
                {canLoadMore ? (
                  <button className="pager-button" type="button" onClick={onLoadMore} disabled={loadingMore}>
                    {loadingMore ? 'Loading fact calls...' : 'Load more fact calls'}
                  </button>
                ) : null}
                {showDashboardRowControls ? (
                  <>
                    <button
                      className="pager-button"
                      type="button"
                      onClick={rowLoadControls.onLoadMoreRows}
                      disabled={!rowLoadControls.canLoadMoreRows || rowLoadControls.refreshing}
                    >
                      {rowLoadControls.refreshing ? 'Loading rows...' : 'Load more dashboard rows'}
                    </button>
                    <button
                      className="pager-button"
                      type="button"
                      onClick={rowLoadControls.onLoadAllRows}
                      disabled={!rowLoadControls.canLoadAllRows || rowLoadControls.refreshing}
                    >
                      Load all dashboard rows
                    </button>
                  </>
                ) : null}
              </div>
            </div>
          ) : null}
        </>
      ) : (
        <p className="empty-state">No aggregate calls are associated with the selected diagnostic fact.</p>
      )}
    </Panel>
  );
}

export function factCallsResult(state: FactCallsState): DiagnosticFactCallsResult | null {
  return 'result' in state && state.result ? state.result : null;
}

function sourceStatusLabel(state: FactLoadState): string {
  if (state.status === 'loaded') {
    return formatNumber(state.payload.total_matched_rows ?? state.payload.rows?.length ?? 0);
  }
  if (state.status === 'loading') return 'Loading';
  if (state.status === 'error') return 'Fallback';
  return 'Static';
}

function factVisibleCountCacheKey(sourceKey: DiagnosticFactSourceKey, factSort: FactSortState): string {
  return `${sourceKey}:${factSort.key}:${factSort.direction}`;
}

function readFactVisibleCount(sourceKey: DiagnosticFactSourceKey, factSort: FactSortState): number {
  try {
    const raw = window.sessionStorage.getItem(FACT_VISIBLE_COUNT_STORAGE_KEY);
    const values = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    const value = Number(values[factVisibleCountCacheKey(sourceKey, factSort)]);
    return Number.isFinite(value) && value > FACT_PREVIEW_COUNT ? Math.round(value) : FACT_PREVIEW_COUNT;
  } catch {
    return FACT_PREVIEW_COUNT;
  }
}

function rememberFactVisibleCount(
  sourceKey: DiagnosticFactSourceKey,
  factSort: FactSortState,
  visibleCount: number,
): void {
  try {
    const raw = window.sessionStorage.getItem(FACT_VISIBLE_COUNT_STORAGE_KEY);
    const values = raw ? (JSON.parse(raw) as Record<string, unknown>) : {};
    values[factVisibleCountCacheKey(sourceKey, factSort)] = Math.max(FACT_PREVIEW_COUNT, Math.round(visibleCount));
    window.sessionStorage.setItem(FACT_VISIBLE_COUNT_STORAGE_KEY, JSON.stringify(values));
  } catch {
    // Keep diagnostics usable when browser storage is unavailable.
  }
}

function formatFactTime(value: string | null | undefined): string {
  if (!value) return 'Unknown';
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp));
}
