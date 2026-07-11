import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type HeatmapVisualizationSpecV1,
} from '../spec';

const fixtureFreshness = { generatedAt: '2026-07-10T12:00:00Z', sourceRevision: 'r4-fixture-v1' };

export const cacheFrontierSpec: CartesianVisualizationSpecV1 = {
  schema: visualizationSpecSchema,
  id: 'cache-frontier',
  title: 'Cache efficiency frontier',
  state: { kind: 'ready' },
  scope: { label: 'Top 12 active threads', rowCount: 8, historyScope: 'active' },
  freshness: fixtureFreshness,
  caveats: ['Thread position reflects observed local calls only.'],
  accessibility: {
    summary: 'Three high-token threads sit below the 35 percent cache frontier and are strong review candidates.',
    keyboardInstructions: 'Use arrow keys to move between threads; press Enter to select the matching table row.',
  },
  table: {
    caption: 'Cache frontier by thread',
    columns: [
      { field: 'thread', label: 'Thread', type: 'text' },
      { field: 'inputTokens', label: 'Input tokens', type: 'number', unit: 'tokens', align: 'right' },
      { field: 'cachePercent', label: 'Cache', type: 'number', unit: 'percent', align: 'right' },
      { field: 'credits', label: 'Credits', type: 'number', unit: 'credits', align: 'right' },
    ],
    defaultSort: { field: 'credits', direction: 'desc' },
  },
  interactions: { selection: { keyField: 'id', labelField: 'thread' }, zoom: { axis: 'both' }, brush: { axis: 'both' } },
  annotations: [
    { id: 'cache-floor', label: '35% cache floor', kind: 'reference-line', axis: 'y', value: 35, severity: 'warning' },
  ],
  kind: 'cartesian',
  data: {
    rows: [
      { id: 't1', thread: 'dashboard-redesign', inputTokens: 1_240_000, cachePercent: 74, credits: 18.4 },
      { id: 't2', thread: 'release-hardening', inputTokens: 980_000, cachePercent: 66, credits: 15.1 },
      { id: 't3', thread: 'allowance-study', inputTokens: 860_000, cachePercent: 42, credits: 14.7 },
      { id: 't4', thread: 'content-index', inputTokens: 1_120_000, cachePercent: 28, credits: 21.9 },
      { id: 't5', thread: 'mcp-experiments', inputTokens: 740_000, cachePercent: 31, credits: 13.8 },
      { id: 't6', thread: 'docs-refresh', inputTokens: 330_000, cachePercent: 81, credits: 4.2 },
      { id: 't7', thread: 'api-refactor', inputTokens: 1_460_000, cachePercent: 24, credits: 27.3 },
      { id: 't8', thread: 'branch-cleanup', inputTokens: 210_000, cachePercent: 58, credits: 3.1 },
    ],
  },
  axes: {
    x: { field: 'inputTokens', label: 'Input tokens', type: 'number', unit: 'tokens', min: 0 },
    y: { field: 'cachePercent', label: 'Cache reuse', type: 'number', unit: 'percent', min: 0, max: 100 },
  },
  series: [
    { id: 'threads', label: 'Threads', mark: 'point', xField: 'inputTokens', yField: 'cachePercent', color: '#2f6fed' },
  ],
};

export const threadLifecycleSpec: CartesianVisualizationSpecV1 = {
  schema: visualizationSpecSchema,
  id: 'thread-lifecycle',
  title: 'Thread lifecycle and context pressure',
  state: { kind: 'ready' },
  scope: { label: 'Selected thread: dashboard-redesign', rowCount: 7, historyScope: 'all' },
  freshness: fixtureFreshness,
  caveats: ['Compaction markers are inferred from local event metadata.'],
  accessibility: {
    summary: 'Context pressure rose across four calls, fell after compaction, then resumed with improved cache reuse.',
    keyboardInstructions: 'Use left and right arrow keys to move through calls in lifecycle order.',
  },
  table: {
    caption: 'Thread lifecycle calls',
    columns: [
      { field: 'call', label: 'Call', type: 'text' },
      { field: 'elapsedMinutes', label: 'Elapsed', type: 'number', unit: 'count', align: 'right' },
      { field: 'contextPercent', label: 'Context', type: 'number', unit: 'percent', align: 'right' },
      { field: 'cachePercent', label: 'Cache', type: 'number', unit: 'percent', align: 'right' },
      { field: 'event', label: 'Lifecycle event', type: 'text' },
    ],
  },
  interactions: { selection: { keyField: 'id', labelField: 'call' }, zoom: { axis: 'x' } },
  annotations: [
    { id: 'compaction', label: 'Compaction', kind: 'reference-line', axis: 'x', value: 62, severity: 'info' },
  ],
  kind: 'cartesian',
  data: {
    rows: [
      { id: 'c1', call: 'Call 1', elapsedMinutes: 0, contextPercent: 18, cachePercent: 12, event: 'Cold start' },
      { id: 'c2', call: 'Call 2', elapsedMinutes: 14, contextPercent: 37, cachePercent: 61, event: 'Warm continuation' },
      { id: 'c3', call: 'Call 3', elapsedMinutes: 31, contextPercent: 58, cachePercent: 72, event: 'Warm continuation' },
      { id: 'c4', call: 'Call 4', elapsedMinutes: 49, contextPercent: 79, cachePercent: 69, event: 'Context pressure' },
      { id: 'c5', call: 'Call 5', elapsedMinutes: 62, contextPercent: 34, cachePercent: 43, event: 'Compaction' },
      { id: 'c6', call: 'Call 6', elapsedMinutes: 78, contextPercent: 47, cachePercent: 76, event: 'Warm continuation' },
      { id: 'c7', call: 'Call 7', elapsedMinutes: 101, contextPercent: 63, cachePercent: 81, event: 'Warm continuation' },
    ],
  },
  axes: {
    x: { field: 'elapsedMinutes', label: 'Minutes since first call', type: 'number', unit: 'count', min: 0 },
    y: { field: 'contextPercent', label: 'Context window', type: 'number', unit: 'percent', min: 0, max: 100 },
  },
  series: [
    { id: 'context', label: 'Context window', mark: 'line', xField: 'elapsedMinutes', yField: 'contextPercent', color: '#7651c9' },
    { id: 'cache', label: 'Cache reuse', mark: 'line', xField: 'elapsedMinutes', yField: 'cachePercent', color: '#16866b' },
  ],
};

export const wasteMatrixSpec: HeatmapVisualizationSpecV1 = {
  schema: visualizationSpecSchema,
  id: 'waste-matrix',
  title: 'Waste fingerprint matrix',
  state: { kind: 'ready' },
  scope: { label: 'Most recent 500 calls', rowCount: 15, historyScope: 'active' },
  freshness: fixtureFreshness,
  caveats: ['Scores rank review priority; they are not direct token counts.'],
  accessibility: {
    summary: 'File rediscovery and shell churn concentrate in three workflows, led by dashboard-redesign.',
    keyboardInstructions: 'Use arrow keys to move across matrix cells and synchronize the evidence table.',
  },
  table: {
    caption: 'Waste fingerprint scores',
    columns: [
      { field: 'workflow', label: 'Workflow', type: 'text' },
      { field: 'pattern', label: 'Pattern', type: 'text' },
      { field: 'score', label: 'Priority score', type: 'number', unit: 'count', align: 'right' },
      { field: 'calls', label: 'Calls', type: 'number', unit: 'count', align: 'right' },
    ],
    defaultSort: { field: 'score', direction: 'desc' },
  },
  interactions: { selection: { keyField: 'id' }, brush: { axis: 'both' } },
  annotations: [],
  kind: 'heatmap',
  encoding: {
    x: { field: 'pattern', label: 'Waste pattern', type: 'category' },
    y: { field: 'workflow', label: 'Workflow', type: 'category' },
    value: { field: 'score', label: 'Priority score', type: 'number', unit: 'count' },
    min: 0,
    max: 100,
  },
  data: {
    rows: [
      { id: 'm1', workflow: 'dashboard-redesign', pattern: 'File rediscovery', score: 91, calls: 23 },
      { id: 'm2', workflow: 'dashboard-redesign', pattern: 'Shell churn', score: 84, calls: 19 },
      { id: 'm3', workflow: 'dashboard-redesign', pattern: 'Low output', score: 57, calls: 8 },
      { id: 'm4', workflow: 'api-refactor', pattern: 'File rediscovery', score: 76, calls: 16 },
      { id: 'm5', workflow: 'api-refactor', pattern: 'Shell churn', score: 62, calls: 11 },
      { id: 'm6', workflow: 'api-refactor', pattern: 'Low output', score: 38, calls: 5 },
      { id: 'm7', workflow: 'content-index', pattern: 'File rediscovery', score: 68, calls: 14 },
      { id: 'm8', workflow: 'content-index', pattern: 'Shell churn', score: 49, calls: 8 },
      { id: 'm9', workflow: 'content-index', pattern: 'Low output', score: 72, calls: 12 },
      { id: 'm10', workflow: 'release-hardening', pattern: 'File rediscovery', score: 31, calls: 6 },
      { id: 'm11', workflow: 'release-hardening', pattern: 'Shell churn', score: 55, calls: 9 },
      { id: 'm12', workflow: 'release-hardening', pattern: 'Low output', score: 26, calls: 4 },
      { id: 'm13', workflow: 'docs-refresh', pattern: 'File rediscovery', score: 43, calls: 7 },
      { id: 'm14', workflow: 'docs-refresh', pattern: 'Shell churn', score: 21, calls: 3 },
      { id: 'm15', workflow: 'docs-refresh', pattern: 'Low output', score: 34, calls: 5 },
    ],
  },
};

export const evidenceLedgerSpec: CartesianVisualizationSpecV1 = {
  schema: visualizationSpecSchema,
  id: 'evidence-ledger',
  title: 'Actionable evidence ledger',
  state: { kind: 'ready' },
  scope: { label: 'Current diagnostic snapshot', rowCount: 6, historyScope: 'active' },
  freshness: fixtureFreshness,
  caveats: ['Impact scores combine token exposure, recurrence, and evidence strength.'],
  accessibility: {
    summary: 'Repeated file rediscovery is the highest-impact finding with strong local evidence.',
    keyboardInstructions: 'Use left and right arrow keys to review findings in impact order.',
  },
  table: {
    caption: 'Actionable evidence findings',
    columns: [
      { field: 'finding', label: 'Finding', type: 'text' },
      { field: 'impact', label: 'Impact', type: 'number', unit: 'count', align: 'right' },
      { field: 'grade', label: 'Evidence grade', type: 'text' },
      { field: 'nextAction', label: 'Next action', type: 'text' },
    ],
    defaultSort: { field: 'impact', direction: 'desc' },
  },
  interactions: { selection: { keyField: 'id', labelField: 'finding' } },
  annotations: [],
  kind: 'cartesian',
  data: {
    rows: [
      { id: 'f1', finding: 'Repeated file rediscovery', impact: 94, grade: 'Strong', nextAction: 'Create a repository map skill' },
      { id: 'f2', finding: 'Shell inspection churn', impact: 81, grade: 'Strong', nextAction: 'Use one structured inspection command' },
      { id: 'f3', finding: 'Large low-output calls', impact: 73, grade: 'Moderate', nextAction: 'Split analysis from implementation' },
      { id: 'f4', finding: 'Cold thread resumes', impact: 62, grade: 'Moderate', nextAction: 'Start a fresh thread from a handoff' },
      { id: 'f5', finding: 'Verbose tool output', impact: 48, grade: 'Limited', nextAction: 'Request compact command output' },
      { id: 'f6', finding: 'Repeated diagnostics reload', impact: 29, grade: 'Resolved', nextAction: 'Keep the new local cache enabled' },
    ],
  },
  axes: {
    x: { field: 'impact', label: 'Impact score', type: 'number', unit: 'count', min: 0, max: 100 },
    y: { field: 'finding', label: 'Finding', type: 'category' },
  },
  series: [{ id: 'impact', label: 'Impact score', mark: 'bar', xField: 'impact', yField: 'finding', color: '#c84652' }],
};
