import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type FlowVisualizationSpecV1,
} from '../spec';

const fixtureFreshness = { generatedAt: '2026-07-10T12:00:00Z', sourceRevision: 'r4-fixture-v1' };

export const allowanceChangePointSpec: CartesianVisualizationSpecV1 = {
  schema: visualizationSpecSchema,
  id: 'allowance-change-point',
  title: 'Weekly allowance regime evidence',
  description: 'Token-derived weekly credit estimates with local confidence ranges and candidate change points.',
  state: { kind: 'ready' },
  scope: { label: 'Eight observed weekly windows', rowCount: 8, historyScope: 'all' },
  freshness: fixtureFreshness,
  caveats: ['This is local evidence, not OpenAI ledger data.', 'Outside usage can create unexplained movement.'],
  accessibility: {
    summary: 'The latest three windows form a lower estimated-credit regime than the preceding five windows.',
    details: ['The candidate shift begins on June 23.', 'Confidence ranges do not overlap for four of the five comparisons.'],
    keyboardInstructions: 'Use left and right arrow keys to move through weekly windows.',
  },
  table: {
    caption: 'Weekly allowance regime evidence',
    columns: [
      { field: 'window', label: 'Window', type: 'time' },
      { field: 'estimate', label: 'Estimated credits', type: 'number', unit: 'credits', align: 'right' },
      { field: 'low', label: 'Low', type: 'number', unit: 'credits', align: 'right' },
      { field: 'high', label: 'High', type: 'number', unit: 'credits', align: 'right' },
      { field: 'grade', label: 'Evidence grade', type: 'text' },
    ],
    defaultSort: { field: 'window', direction: 'asc' },
  },
  interactions: {
    selection: { keyField: 'id', labelField: 'window' },
    zoom: { axis: 'x', startPercent: 18, endPercent: 100 },
    brush: { axis: 'x' },
  },
  annotations: [
    {
      id: 'candidate-shift',
      label: 'Candidate lower regime',
      kind: 'reference-line',
      axis: 'x',
      value: '2026-06-23',
      severity: 'warning',
      evidenceKeys: ['week-06-23', 'week-06-30'],
    },
    {
      id: 'missing-observation',
      label: 'Sparse observations',
      kind: 'range',
      axis: 'x',
      start: '2026-06-02',
      end: '2026-06-09',
      severity: 'neutral',
    },
  ],
  kind: 'cartesian',
  data: {
    rows: [
      { id: 'week-05-19', window: '2026-05-19', estimate: 116, low: 109, high: 123, grade: 'Moderate' },
      { id: 'week-05-26', window: '2026-05-26', estimate: 119, low: 112, high: 126, grade: 'Strong' },
      { id: 'week-06-02', window: '2026-06-02', estimate: 114, low: 105, high: 124, grade: 'Limited' },
      { id: 'week-06-09', window: '2026-06-09', estimate: 117, low: 110, high: 124, grade: 'Moderate' },
      { id: 'week-06-16', window: '2026-06-16', estimate: 115, low: 108, high: 122, grade: 'Strong' },
      { id: 'week-06-23', window: '2026-06-23', estimate: 93, low: 87, high: 99, grade: 'Moderate' },
      { id: 'week-06-30', window: '2026-06-30', estimate: 91, low: 85, high: 97, grade: 'Strong' },
      { id: 'week-07-07', window: '2026-07-07', estimate: 94, low: 88, high: 100, grade: 'Moderate' },
    ],
  },
  axes: {
    x: { field: 'window', label: 'Weekly window', type: 'time', unit: 'timestamp' },
    y: { field: 'estimate', label: 'Estimated credits', type: 'number', unit: 'credits', min: 70, max: 135 },
  },
  series: [
    {
      id: 'estimate',
      label: 'Estimated weekly credits',
      mark: 'line',
      xField: 'window',
      yField: 'estimate',
      lowerField: 'low',
      upperField: 'high',
      color: '#2f6fed',
      smooth: true,
    },
  ],
};

export const tokenFlowSpec: FlowVisualizationSpecV1 = {
  schema: visualizationSpecSchema,
  id: 'token-flow',
  title: 'Where loaded tokens go',
  description: 'A local token-flow accounting from loaded input through reuse, reasoning, output, and discarded context.',
  state: { kind: 'ready' },
  scope: { label: 'Most recent 500 calls', rowCount: 7, historyScope: 'active' },
  freshness: fixtureFreshness,
  caveats: ['Flow widths represent token volume, not billed cost.'],
  accessibility: {
    summary: 'Cached reuse is the largest destination, while repeated context is the largest avoidable branch.',
    keyboardInstructions: 'Use up and down arrow keys to move through flow links in the evidence table.',
  },
  table: {
    caption: 'Token flow links',
    columns: [
      { field: 'source', label: 'From', type: 'text' },
      { field: 'target', label: 'To', type: 'text' },
      { field: 'value', label: 'Tokens', type: 'number', unit: 'tokens', align: 'right' },
      { field: 'evidenceKey', label: 'Evidence key', type: 'text' },
    ],
    defaultSort: { field: 'value', direction: 'desc' },
  },
  interactions: { selection: { keyField: 'id' } },
  annotations: [],
  kind: 'flow',
  encoding: {
    sourceLabel: 'Source',
    targetLabel: 'Destination',
    valueLabel: 'Tokens',
    valueUnit: 'tokens',
  },
  data: {
    nodes: [
      { id: 'loaded', label: 'Loaded input', color: '#2f6fed' },
      { id: 'cached', label: 'Cached reuse', color: '#16866b' },
      { id: 'uncached', label: 'Uncached context', color: '#9a5900' },
      { id: 'reasoning', label: 'Reasoning', color: '#7651c9' },
      { id: 'output', label: 'Visible output', color: '#16866b' },
      { id: 'tool', label: 'Tool output', color: '#5c6675' },
      { id: 'repeated', label: 'Repeated context', color: '#c84652' },
    ],
    links: [
      { id: 'flow-1', source: 'loaded', target: 'cached', value: 6_850_000, evidenceKey: 'cache:reused' },
      { id: 'flow-2', source: 'loaded', target: 'uncached', value: 3_180_000, evidenceKey: 'cache:miss' },
      { id: 'flow-3', source: 'uncached', target: 'reasoning', value: 1_160_000, evidenceKey: 'reasoning:input' },
      { id: 'flow-4', source: 'uncached', target: 'tool', value: 720_000, evidenceKey: 'tools:output' },
      { id: 'flow-5', source: 'uncached', target: 'repeated', value: 1_300_000, evidenceKey: 'context:repeat' },
      { id: 'flow-6', source: 'reasoning', target: 'output', value: 384_000, evidenceKey: 'output:assistant' },
      { id: 'flow-7', source: 'tool', target: 'output', value: 210_000, evidenceKey: 'output:tool-summary' },
    ],
  },
};
