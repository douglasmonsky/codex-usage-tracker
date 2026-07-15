export const visualizationSpecSchema = 'codex-usage-visualization/v1' as const;

export type VisualizationValue = string | number | boolean | null;
export type VisualizationRecord = Readonly<Record<string, VisualizationValue>>;

export type VisualizationDataState =
  | { kind: 'ready' }
  | { kind: 'loading'; message?: string }
  | { kind: 'empty'; message: string }
  | { kind: 'partial'; message: string; availableRows: number; expectedRows?: number }
  | { kind: 'insufficient-data'; message: string; requiredRows?: number; availableRows?: number }
  | { kind: 'stale'; message: string; lastUpdatedAt?: string }
  | { kind: 'error'; message: string; retryable: boolean };

export type VisualizationUnit =
  | 'count'
  | 'credits'
  | 'credits_per_percent'
  | 'percent'
  | 'ratio'
  | 'seconds'
  | 'timestamp'
  | 'tokens'
  | 'usd';

export type VisualizationFieldType = 'category' | 'number' | 'text' | 'time';

export type VisualizationField = {
  field: string;
  label: string;
  type: VisualizationFieldType;
  unit?: VisualizationUnit;
};

export type VisualizationTableColumn = VisualizationField & {
  align?: 'left' | 'right';
  hiddenByDefault?: boolean;
};

export type VisualizationTableSpec = {
  caption: string;
  columns: VisualizationTableColumn[];
  defaultSort?: { field: string; direction: 'asc' | 'desc' };
};

export type VisualizationAccessibility = {
  summary: string;
  details?: string[];
  keyboardInstructions?: string;
};

export type VisualizationScope = {
  label: string;
  rowCount: number;
  historyScope?: 'active' | 'all';
  filters?: string[];
};

export type VisualizationFreshness = {
  generatedAt: string;
  sourceRevision?: string;
};

export type VisualizationInteractionSpec = {
  selection?: { keyField: string; labelField?: string };
  zoom?: { axis: 'x' | 'y' | 'both'; startPercent?: number; endPercent?: number };
  brush?: { axis: 'x' | 'y' | 'both' };
};

export type VisualizationAnnotation = {
  id: string;
  label: string;
  kind: 'point' | 'reference-line' | 'range';
  axis?: 'x' | 'y';
  value?: VisualizationValue;
  start?: VisualizationValue;
  end?: VisualizationValue;
  x?: VisualizationValue;
  y?: VisualizationValue;
  severity?: 'neutral' | 'info' | 'warning' | 'critical';
  evidenceKeys?: string[];
};

type VisualizationSpecBaseV1 = {
  schema: typeof visualizationSpecSchema;
  id: string;
  title: string;
  description?: string;
  state: VisualizationDataState;
  scope: VisualizationScope;
  freshness: VisualizationFreshness;
  caveats?: string[];
  accessibility: VisualizationAccessibility;
  table: VisualizationTableSpec;
  interactions?: VisualizationInteractionSpec;
  annotations?: VisualizationAnnotation[];
};

export type VisualizationAxis = VisualizationField & {
  min?: number;
  max?: number;
};

export type CartesianSeriesSpec = {
  id: string;
  label: string;
  mark: 'bar' | 'line' | 'point';
  xField: string;
  yField: string;
  color?: string;
  lineWidth?: number;
  pointStyle?: 'filled' | 'hollow' | 'none';
  showPoints?: boolean;
  stack?: string;
  smooth?: boolean;
  lowerField?: string;
  upperField?: string;
};

export type CartesianVisualizationSpecV1 = VisualizationSpecBaseV1 & {
  kind: 'cartesian';
  data: { rows: VisualizationRecord[] };
  axes: { x: VisualizationAxis; y: VisualizationAxis };
  series: CartesianSeriesSpec[];
  showLegend?: boolean;
};

export type HeatmapVisualizationSpecV1 = VisualizationSpecBaseV1 & {
  kind: 'heatmap';
  data: { rows: VisualizationRecord[] };
  encoding: {
    x: VisualizationField;
    y: VisualizationField;
    value: VisualizationField;
    min?: number;
    max?: number;
  };
};

export type FlowNode = {
  id: string;
  label: string;
  category?: string;
  color?: string;
};

export type FlowLink = {
  id: string;
  source: string;
  target: string;
  value: number;
  evidenceKey?: string;
};

export type FlowVisualizationSpecV1 = VisualizationSpecBaseV1 & {
  kind: 'flow';
  data: { nodes: FlowNode[]; links: FlowLink[] };
  encoding: {
    sourceLabel: string;
    targetLabel: string;
    valueLabel: string;
    valueUnit?: VisualizationUnit;
  };
};

export type VisualizationSpecV1 =
  | CartesianVisualizationSpecV1
  | FlowVisualizationSpecV1
  | HeatmapVisualizationSpecV1;

export type VisualizationSpecIssue = {
  path: string;
  message: string;
};
