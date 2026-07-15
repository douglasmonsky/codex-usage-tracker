import type {
  CartesianVisualizationSpecV1,
  FlowVisualizationSpecV1,
  HeatmapVisualizationSpecV1,
  VisualizationAccessibility,
  VisualizationAnnotation,
  VisualizationDataState,
  VisualizationRecord,
  VisualizationSpecV1,
  VisualizationTableSpec,
} from '../spec';
import { visualizationAriaDescription } from '../spec';

type Translate = (value: string) => string;

export function localizeVisualizationSpec(
  spec: VisualizationSpecV1,
  translate: Translate,
): VisualizationSpecV1 {
  const base = {
    title: translate(spec.title),
    description: spec.description ? translate(spec.description) : undefined,
    state: localizeState(spec.state, translate),
    scope: {
      ...spec.scope,
      label: translate(spec.scope.label),
      filters: spec.scope.filters?.map(translate),
    },
    caveats: spec.caveats?.map(translate),
    accessibility: {
      ...localizeAccessibility(spec.accessibility, translate),
      description: visualizationAriaDescription(spec, translate),
    },
    table: localizeTable(spec.table, translate),
    annotations: spec.annotations?.map(annotation => localizeAnnotation(annotation, translate)),
  };

  if (spec.kind === 'cartesian') {
    const rows = localizeRows(spec.data.rows, spec.table, translate);
    return {
      ...spec,
      ...base,
      kind: 'cartesian',
      data: rows === spec.data.rows ? spec.data : { rows },
      axes: {
        x: { ...spec.axes.x, label: translate(spec.axes.x.label) },
        y: { ...spec.axes.y, label: translate(spec.axes.y.label) },
      },
      series: spec.series.map(series => ({ ...series, label: translate(series.label) })),
    } satisfies CartesianVisualizationSpecV1;
  }
  if (spec.kind === 'heatmap') {
    const rows = localizeRows(spec.data.rows, spec.table, translate);
    return {
      ...spec,
      ...base,
      kind: 'heatmap',
      data: rows === spec.data.rows ? spec.data : { rows },
      encoding: {
        ...spec.encoding,
        x: { ...spec.encoding.x, label: translate(spec.encoding.x.label) },
        y: { ...spec.encoding.y, label: translate(spec.encoding.y.label) },
        value: { ...spec.encoding.value, label: translate(spec.encoding.value.label) },
      },
    } satisfies HeatmapVisualizationSpecV1;
  }
  return {
    ...spec,
    ...base,
    kind: 'flow',
    data: {
      ...spec.data,
      nodes: spec.data.nodes.map(node => ({ ...node, label: translate(node.label) })),
    },
    encoding: {
      ...spec.encoding,
      sourceLabel: translate(spec.encoding.sourceLabel),
      targetLabel: translate(spec.encoding.targetLabel),
      valueLabel: translate(spec.encoding.valueLabel),
    },
  } satisfies FlowVisualizationSpecV1;
}

function localizeState(state: VisualizationDataState, translate: Translate): VisualizationDataState {
  if (state.kind === 'ready') return state;
  if (state.kind === 'loading') {
    return { ...state, message: state.message ? translate(state.message) : undefined };
  }
  return { ...state, message: translate(state.message) };
}

function localizeAccessibility(
  accessibility: VisualizationAccessibility,
  translate: Translate,
): VisualizationAccessibility {
  return {
    ...accessibility,
    summary: translate(accessibility.summary),
    details: accessibility.details?.map(translate),
    keyboardInstructions: accessibility.keyboardInstructions
      ? translate(accessibility.keyboardInstructions)
      : undefined,
  };
}

function localizeTable(table: VisualizationTableSpec, translate: Translate): VisualizationTableSpec {
  return {
    ...table,
    caption: translate(table.caption),
    columns: table.columns.map(column => ({ ...column, label: translate(column.label) })),
  };
}

function localizeAnnotation(
  annotation: VisualizationAnnotation,
  translate: Translate,
): VisualizationAnnotation {
  return { ...annotation, label: translate(annotation.label) };
}

const protectedDataFields = new Set([
  'branch', 'command', 'cwd', 'date', 'file', 'id', 'key', 'model', 'name', 'observed',
  'path', 'project', 'record_id', 'remote', 'session', 'source', 'thread', 'time', 'timestamp', 'window',
]);

function localizeRows(
  rows: VisualizationRecord[],
  table: VisualizationTableSpec,
  translate: Translate,
): VisualizationRecord[] {
  if (!rows.length) return rows;
  const localizableFields = new Set(
    table.columns
      .filter(column => (column.type === 'category' || column.type === 'text') && !protectedDataFields.has(column.field))
      .map(column => column.field),
  );
  if (!localizableFields.size) return rows;
  let changed = false;
  const localized = rows.map(row => {
    let next: Record<string, string | number | boolean | null> | null = null;
    for (const field of localizableFields) {
      const value = row[field];
      if (typeof value !== 'string') continue;
      const translated = translate(value);
      if (translated === value) continue;
      next ??= { ...row };
      next[field] = translated;
      changed = true;
    }
    return next ?? row;
  });
  return changed ? localized : rows;
}
