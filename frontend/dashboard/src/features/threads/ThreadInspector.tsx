import { Copy, Search } from 'lucide-react';
import { useMemo } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import type { CallRow, ThreadRow } from '../../api/types';
import { DonutChart } from '../../charts/DonutChart';
import { Panel } from '../../components/Panel';
import { CallSignalPucks } from '../shared/tables';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';
import {
  callPricingStatusText,
  computeThreadImpact,
  computeThreadLifecycle,
  computeThreadRelationships,
  computeThreadStatus,
  countThreadEfficiencySignals,
  formatCallContextUse,
  formatCredits,
  formatTrendPct,
  sortThreadCalls,
  timelineSeverityClass,
  timelineWidth,
} from './threadAnalysis';
import { threadCallPageSize, type ThreadCallSortDirection, type ThreadCallSortKey } from './threadsUrlState';

type ThreadInspectorProps = {
  selected: ThreadRow | null;
  calls: CallRow[];
  allCalls: CallRow[];
  totalCallCount: number;
  hasMoreCalls: boolean;
  isFetchingMoreCalls: boolean;
  callSort: ThreadCallSortKey;
  callSortDirection: ThreadCallSortDirection;
  visibleCallCount: number;
  onCallSortChange(value: string): void;
  onCallSortDirectionChange(value: string): void;
  onVisibleCallCountChange(count: number | ((current: number) => number)): void;
  onLoadMoreCalls(): void;
  onOpenInvestigator(recordId: string): void;
  onCopyCallLink(recordId: string): void;
};

export function ThreadInspector({
  selected,
  calls,
  allCalls,
  totalCallCount,
  hasMoreCalls,
  isFetchingMoreCalls,
  callSort,
  callSortDirection,
  visibleCallCount,
  onCallSortChange,
  onCallSortDirectionChange,
  onVisibleCallCountChange,
  onLoadMoreCalls,
  onOpenInvestigator,
  onCopyCallLink,
}: ThreadInspectorProps) {
  const shellI18n = useShellI18n();
  const sortedCalls = useMemo(
    () => sortThreadCalls(calls, callSort, callSortDirection), [calls, callSort, callSortDirection],
  );
  const lifecycle = useMemo(
    () => computeThreadLifecycle(calls, selected?.name ?? ''), [calls, selected?.name],
  );
  const status = useMemo(() => computeThreadStatus(calls, selected, lifecycle), [calls, lifecycle, selected]);
  const relationships = useMemo(
    () => computeThreadRelationships(calls, allCalls, selected?.name ?? ''),
    [allCalls, calls, selected?.name],
  );
  const efficiencySignalCount = useMemo(() => countThreadEfficiencySignals(calls), [calls]);
  const impact = useMemo(
    () => computeThreadImpact(selected, status, relationships, efficiencySignalCount),
    [efficiencySignalCount, relationships, selected, status],
  );
  const visibleCalls = sortedCalls.slice(0, visibleCallCount);
  const hiddenLoadedCallCount = Math.max(sortedCalls.length - visibleCalls.length, 0);
  const remainingCallCount = Math.max(totalCallCount - visibleCalls.length, 0);
  const nextThreadCallBatchCount = Math.min(threadCallPageSize, remainingCallCount);

  if (!selected) {
    return (
      <aside className="side-panel">
        <Panel title="Selected Thread" subtitle="No matching thread">
          <p className="empty-state">No grouped thread matches the active filters.</p>
        </Panel>
      </aside>
    );
  }

  return (
    <aside className="side-panel">
      <Panel title="Selected Thread" subtitle={selected.name}>
        <div className="thread-call-list">
          <div className="section-heading compact">
            <h3>Thread Calls</h3>
            <span>
              {sortedCalls.length
                ? `${visibleCalls.length} of ${totalCallCount} loaded`
                : 'No loaded calls'}
            </span>
          </div>
          {sortedCalls.length ? (
            <>
              <ThreadCallControls
                callSort={callSort}
                callSortDirection={callSortDirection}
                onCallSortChange={onCallSortChange}
                onCallSortDirectionChange={onCallSortDirectionChange}
              />
              <ol className="thread-mini-timeline">
                {visibleCalls.map(call => (
                  <ThreadCallRow
                    key={call.id}
                    call={call}
                    onOpenInvestigator={onOpenInvestigator}
                    onCopyCallLink={onCopyCallLink}
                  />
                ))}
              </ol>
              <div className="thread-call-pager">
                <button
                  className="toolbar-button"
                  type="button"
                  onClick={() => {
                    if (hiddenLoadedCallCount) {
                      onVisibleCallCountChange(
                        current => Math.min(current + threadCallPageSize, sortedCalls.length),
                      );
                    } else {
                      onLoadMoreCalls();
                    }
                  }}
                  disabled={!hiddenLoadedCallCount && !hasMoreCalls || isFetchingMoreCalls}
                >
                  {isFetchingMoreCalls
                    ? 'Loading more calls'
                    : `Show ${formatNumber(nextThreadCallBatchCount || threadCallPageSize)} more calls`}
                </button>
                {visibleCallCount > threadCallPageSize ? (
                  <button
                    className="toolbar-button"
                    type="button"
                    onClick={() => onVisibleCallCountChange(threadCallPageSize)}
                  >
                    Show first {threadCallPageSize}
                  </button>
                ) : null}
                <span>{remainingCallCount ? `${remainingCallCount} more available` : 'All calls visible'}</span>
              </div>
            </>
          ) : (
            <p className="empty-state">No loaded aggregate call rows belong to this thread.</p>
          )}
        </div>
        <div className="detail-stat-grid vertical">
          <span><strong>{selected.turns}</strong>Turns visible</span>
          <span><strong>{money(selected.cost)}</strong>Estimated cost</span>
          <span><strong>{pct(selected.cachePct)}</strong>Cache hit rate</span>
          <span><strong>{formatCompact(selected.totalTokens)}</strong>Total tokens</span>
          <span><strong>{selected.totalDuration}</strong>Total duration</span>
          <span><strong>{selected.averageGap}</strong>Average gap</span>
          <span><strong>{selected.initiatorSummary}</strong>Initiated by</span>
          <span><strong>{selected.modelSummary}</strong>Models</span>
          <span><strong>{shellI18n.translateText(selected.effortSummary)}</strong>Effort mix</span>
          <span>
            <strong>{formatCompact(selected.cachedInput)} / {formatCompact(selected.uncachedInput)}</strong>
            Cached / uncached input
          </span>
          <span><strong>{formatCompact(selected.reasoningOutput)}</strong>Reasoning output</span>
          <span>
            <strong>{selected.contextPct == null ? '-' : pct(selected.contextPct)}</strong>
            Peak context
          </span>
        </div>
        <DonutChart
          centerLabel="Risk Mix"
          data={[
            {
              label: 'Cold risk',
              value: selected.coldResumeRisk === 'High' ? 55 : selected.coldResumeRisk === 'Medium' ? 35 : 15,
              color: '#f59e0b',
            },
            { label: 'Cache reuse', value: selected.cachePct, color: '#2563eb' },
            { label: 'Productivity', value: selected.productivity, color: '#059669' },
          ]}
        />
        <div className="thread-status-card">
          <div className="section-heading compact">
            <h3>Thread Status</h3>
            <span>{status.nextAction}</span>
          </div>
          <div className="status-thread-grid">
            <span><strong>{status.pricingStatus}</strong>Pricing status</span>
            <span><strong>{status.creditStatus}</strong>Credit status</span>
            <span><strong>{status.cacheStatus}</strong>Cache ratio</span>
            <span><strong>{status.contextStatus}</strong>Max context use</span>
            <span>
              <strong>{status.nextAction}</strong>
              {shellI18n.t('detail.next_action', 'Next action')}
            </span>
          </div>
        </div>
        {impact ? (
          <div className="thread-impact-card">
            <div className="section-heading compact">
              <h3>Thread Impact</h3>
              <span>{impact.allowanceImpact}</span>
            </div>
            <div className="impact-thread-grid">
              <span><strong>{impact.codexCredits}</strong>Codex credits</span>
              <span><strong>{impact.allowanceImpact}</strong>Allowance impact</span>
              <span><strong>{impact.attentionScore}</strong>Attention score</span>
              <span><strong>{impact.costPerCall}</strong>Cost per call</span>
            </div>
          </div>
        ) : null}
        <div className="thread-lifecycle-card">
          <div className="section-heading compact">
            <h3>Thread Lifecycle</h3>
            <span>{lifecycle.subagentBeforeSpike ? 'Subagent before spike' : 'Aggregate trend'}</span>
          </div>
          <div className="lifecycle-grid">
            <span>
              <strong>
                {lifecycle.firstExpensive
                  ? shellI18n.translateText(`${lifecycle.firstExpensive.call.time} · Call ${lifecycle.firstExpensive.index + 1}`)
                  : 'None'}
              </strong>
              First expensive turn
            </span>
            <span>
              <strong>
                {lifecycle.largestJump
                  ? shellI18n.translateText(`${formatCompact(lifecycle.largestJump.tokens)} at ${lifecycle.largestJump.call.time}`)
                  : 'None'}
              </strong>
              Largest token jump
            </span>
            <span><strong>{formatTrendPct(lifecycle.cacheTrend)}</strong>Cache trend</span>
            <span><strong>{formatTrendPct(lifecycle.contextTrend)}</strong>Context trend</span>
          </div>
        </div>
        <div className="thread-relationships-card">
          <div className="section-heading compact">
            <h3>Relationships</h3>
            <span>
              {relationships.spawnedThreads
                ? `${relationships.spawnedThreads} spawned`
                : 'Loaded aggregate links'}
            </span>
          </div>
          <div className="relationship-grid">
            <span><strong>{relationships.parentThreadLabel || 'None'}</strong>Spawned from</span>
            <span><strong>{relationships.subagentCalls}</strong>Subagent calls</span>
            <span><strong>{relationships.autoReviewCalls}</strong>Auto-review calls</span>
            <span><strong>{relationships.attachedCalls}</strong>Attached calls</span>
            <span><strong>{relationships.spawnedThreads}</strong>Spawned threads</span>
            <span><strong>{relationships.spawnedChildCalls}</strong>Spawned child calls</span>
          </div>
        </div>
        <div className="thread-secondary-card">
          <div className="section-heading compact">
            <h3>Thread Fields</h3>
            <span>{efficiencySignalCount ? `${efficiencySignalCount} signals` : 'Aggregate summary'}</span>
          </div>
          <div className="secondary-thread-grid">
            <span><strong>{shellI18n.translateText(selected.latestActivity)}</strong>Latest activity</span>
            <span><strong>{formatCompact(selected.totalTokens)}</strong>Total tokens</span>
            <span><strong>{calls.length}</strong>Loaded calls</span>
            <span><strong>{efficiencySignalCount}</strong>Efficiency signals</span>
            <span><strong>{selected.modelSummary}</strong>Model mix</span>
            <span><strong>{shellI18n.translateText(selected.effortSummary)}</strong>Effort mix</span>
          </div>
        </div>
      </Panel>
    </aside>
  );
}

function ThreadCallControls({
  callSort,
  callSortDirection,
  onCallSortChange,
  onCallSortDirectionChange,
}: Pick<
  ThreadInspectorProps,
  'callSort' | 'callSortDirection' | 'onCallSortChange' | 'onCallSortDirectionChange'
>) {
  return (
    <div className="thread-call-controls">
      <label className="mini-select-field">
        <span>Sort calls</span>
        <select
          aria-label="Sort thread calls"
          value={callSort}
          onChange={event => onCallSortChange(event.target.value)}
        >
          <option value="newest">Newest</option>
          <option value="duration">Duration</option>
          <option value="gap">Previous gap</option>
          <option value="initiator">Initiator</option>
          <option value="model">Model</option>
          <option value="effort">Effort</option>
          <option value="tokens">Most tokens</option>
          <option value="cached">Cached input</option>
          <option value="uncached">Uncached input</option>
          <option value="output">Output</option>
          <option value="reasoning">Reasoning</option>
          <option value="cost">Highest cost</option>
          <option value="cache">Lowest cache</option>
        </select>
      </label>
      <label className="mini-select-field">
        <span>Direction</span>
        <select
          aria-label="Sort thread calls direction"
          value={callSortDirection}
          onChange={event => onCallSortDirectionChange(event.target.value)}
        >
          <option value="desc">Descending</option>
          <option value="asc">Ascending</option>
        </select>
      </label>
    </div>
  );
}

function ThreadCallRow({
  call,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  call: CallRow;
  onOpenInvestigator(recordId: string): void;
  onCopyCallLink(recordId: string): void;
}) {
  const i18n = useShellI18n();
  const openLabel = `Open investigator for thread call ${call.thread} ${call.model}`;
  const copyLabel = `Copy link for thread call ${call.thread} ${call.model}`;
  return (
    <li
      className="thread-call-row has-row-action"
      tabIndex={0}
      aria-label={openLabel}
      onClick={() => onOpenInvestigator(call.id)}
      onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          onOpenInvestigator(call.id);
        }
      }}
    >
      <span>{i18n.translateText(call.time)}</span>
      <strong>{call.model} / {i18n.translateText(call.effort)}</strong>
      <em>{i18n.translateText(`${formatCompact(call.totalTokens)} tokens - ${pct(call.cachedPct)} cache - ${money(call.cost)}`)}</em>
      <div className="thread-call-flags">
        <CallSignalPucks call={call} />
        <span>{i18n.translateText(`Context ${formatCallContextUse(call)}`)}</span>
        <span>{i18n.translateText(callPricingStatusText(call))}</span>
      </div>
      <div className="thread-call-meta">
        <span>{call.duration}</span>
        <span>{i18n.translateText(`Prev ${call.previousCallGap}`)}</span>
        <span>{i18n.translateText(`${call.initiator || 'unknown'} initiated`)}</span>
        <span>{i18n.translateText(formatCredits(call.credits))}</span>
      </div>
      {call.recommendation ? <p className="thread-call-recommendation">{i18n.translateText(call.recommendation)}</p> : null}
      <div className="thread-context-bar" role="img" aria-label={`Context use ${formatCallContextUse(call)}`}>
        <span
          className={timelineSeverityClass(call.contextWindowPct)}
          style={{ width: timelineWidth(call.contextWindowPct) }}
        />
      </div>
      <div className="thread-call-actions table-action-group">
        <button
          className="table-action-button"
          type="button"
          aria-label={openLabel}
          onKeyDown={stopRowActionKeyDown}
          onClick={event => {
            event.stopPropagation();
            onOpenInvestigator(call.id);
          }}
        >
          <Search size={14} />
          Open
        </button>
        <button
          className="table-action-button"
          type="button"
          aria-label={copyLabel}
          onKeyDown={stopRowActionKeyDown}
          onClick={event => {
            event.stopPropagation();
            onCopyCallLink(call.id);
          }}
        >
          <Copy size={14} />
          Copy
        </button>
      </div>
    </li>
  );
}
