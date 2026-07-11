import type { CallRow, ThreadRow } from '../../api/types';
import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type VisualizationDataState,
} from '../../visualization';

export function buildCacheFrontierSpec(
  threads: ThreadRow[],
  historyScope: 'active' | 'all',
  sourceRevision: string,
): CartesianVisualizationSpecV1 {
  const rows = threads.map(thread => ({
    id: thread.name,
    thread: thread.name,
    inputTokens: thread.cachedInput + thread.uncachedInput,
    cachePercent: thread.cachePct,
    credits: thread.credits,
    totalTokens: thread.totalTokens,
  }));
  return {
    schema: visualizationSpecSchema,
    id: 'thread-cache-frontier',
    title: 'Cache efficiency frontier',
    description: 'Threads further right carry more input; threads lower on the plot reuse less of it.',
    state: dataState(rows.length, 'No threads match the current scope.'),
    scope: { label: `${threads.length.toLocaleString()} loaded threads`, rowCount: rows.length, historyScope },
    freshness: { generatedAt: sourceRevision || latestThreadTime(threads), sourceRevision },
    caveats: ['Credits and cost remain estimates when exact rate metadata is unavailable.'],
    accessibility: {
      summary: cacheFrontierSummary(threads),
      keyboardInstructions: 'Use arrow keys to move between threads; press Enter to synchronize the selected row.',
    },
    table: {
      caption: 'Cache efficiency by thread',
      columns: [
        { field: 'thread', label: 'Thread', type: 'text' },
        { field: 'inputTokens', label: 'Input tokens', type: 'number', unit: 'tokens', align: 'right' },
        { field: 'cachePercent', label: 'Cache', type: 'number', unit: 'percent', align: 'right' },
        { field: 'credits', label: 'Credits', type: 'number', unit: 'credits', align: 'right' },
        { field: 'totalTokens', label: 'Total tokens', type: 'number', unit: 'tokens', align: 'right' },
      ],
      defaultSort: { field: 'totalTokens', direction: 'desc' },
    },
    interactions: { selection: { keyField: 'id', labelField: 'thread' }, zoom: { axis: 'both' }, brush: { axis: 'both' } },
    annotations: [{ id: 'cache-floor', label: '35% review floor', kind: 'reference-line', axis: 'y', value: 35, severity: 'warning' }],
    kind: 'cartesian',
    data: { rows },
    axes: {
      x: { field: 'inputTokens', label: 'Input tokens', type: 'number', unit: 'tokens', min: 0 },
      y: { field: 'cachePercent', label: 'Cache reuse', type: 'number', unit: 'percent', min: 0, max: 100 },
    },
    series: [{ id: 'threads', label: 'Threads', mark: 'point', xField: 'inputTokens', yField: 'cachePercent', color: '#2f6fed' }],
  };
}

export function buildThreadLifecycleSpec(
  calls: CallRow[],
  threadName: string,
  historyScope: 'active' | 'all',
  sourceRevision: string,
): CartesianVisualizationSpecV1 {
  const ordered = [...calls].sort((left, right) => callTime(left) - callTime(right));
  const firstTime = callTime(ordered[0]);
  const rows = ordered.map((call, index) => ({
    id: call.id,
    call: `Call ${index + 1}`,
    elapsedMinutes: Math.max(0, Math.round((callTime(call) - firstTime) / 60_000)),
    contextPercent: call.contextWindowPct,
    cachePercent: call.cachedPct,
    totalTokens: call.totalTokens,
    event: lifecycleEvent(call, index),
  }));
  const contextRows = rows.filter(row => typeof row.contextPercent === 'number');
  return {
    schema: visualizationSpecSchema,
    id: 'selected-thread-lifecycle',
    title: 'Thread lifecycle',
    description: 'Context pressure and cache reuse across the selected thread.',
    state: dataState(contextRows.length, 'Context-window evidence is unavailable for this thread.'),
    scope: { label: threadName || 'No thread selected', rowCount: rows.length, historyScope },
    freshness: { generatedAt: sourceRevision || ordered.at(-1)?.eventTimestamp || '', sourceRevision },
    caveats: ['Lifecycle labels are inferred from aggregate timing, cache, and context fields.'],
    accessibility: {
      summary: lifecycleSummary(ordered, threadName),
      keyboardInstructions: 'Use left and right arrow keys to move through calls in lifecycle order.',
    },
    table: {
      caption: 'Selected thread lifecycle calls',
      columns: [
        { field: 'call', label: 'Call', type: 'text' },
        { field: 'elapsedMinutes', label: 'Elapsed', type: 'number', unit: 'count', align: 'right' },
        { field: 'contextPercent', label: 'Context', type: 'number', unit: 'percent', align: 'right' },
        { field: 'cachePercent', label: 'Cache', type: 'number', unit: 'percent', align: 'right' },
        { field: 'totalTokens', label: 'Tokens', type: 'number', unit: 'tokens', align: 'right' },
        { field: 'event', label: 'Lifecycle event', type: 'text' },
      ],
    },
    interactions: { selection: { keyField: 'id', labelField: 'call' }, zoom: { axis: 'x' } },
    kind: 'cartesian',
    data: { rows },
    axes: {
      x: { field: 'elapsedMinutes', label: 'Minutes since first call', type: 'number', unit: 'count', min: 0 },
      y: { field: 'contextPercent', label: 'Context / cache', type: 'number', unit: 'percent', min: 0, max: 100 },
    },
    series: [
      { id: 'context', label: 'Context window', mark: 'line', xField: 'elapsedMinutes', yField: 'contextPercent', color: '#7651c9' },
      { id: 'cache', label: 'Cache reuse', mark: 'line', xField: 'elapsedMinutes', yField: 'cachePercent', color: '#16866b' },
    ],
  };
}

function dataState(rows: number, emptyMessage: string): VisualizationDataState {
  return rows ? { kind: 'ready' } : { kind: 'empty', message: emptyMessage };
}

function latestThreadTime(threads: ThreadRow[]): string {
  return [...threads].sort((left, right) => Date.parse(right.latestActivityRaw) - Date.parse(left.latestActivityRaw))[0]?.latestActivityRaw || '';
}

function cacheFrontierSummary(threads: ThreadRow[]): string {
  const reviewCount = threads.filter(thread => thread.cachePct < 35 && thread.totalTokens >= 50_000).length;
  return reviewCount
    ? `${reviewCount} loaded threads combine at least 50,000 tokens with less than 35 percent cache reuse.`
    : 'No loaded high-token thread falls below the 35 percent cache review floor.';
}

function lifecycleSummary(calls: CallRow[], threadName: string): string {
  if (!calls.length) return `No loaded calls are available for ${threadName || 'the selected thread'}.`;
  const peak = Math.max(...calls.map(call => call.contextWindowPct ?? 0));
  return `${calls.length} calls are available for ${threadName}; peak observed context use is ${peak.toFixed(1)} percent.`;
}

function lifecycleEvent(call: CallRow, index: number): string {
  if (index === 0) return 'Thread start';
  if (call.previousCallGapSeconds >= 3_600) return 'Cold resume';
  if ((call.contextWindowPct ?? 0) >= 80) return 'Context pressure';
  if (call.cachedPct >= 60) return 'Warm continuation';
  return 'Continuation';
}

function callTime(call?: CallRow): number {
  if (!call) return 0;
  const parsed = Date.parse(call.eventTimestamp || call.rawTime || call.time);
  return Number.isFinite(parsed) ? parsed : 0;
}
