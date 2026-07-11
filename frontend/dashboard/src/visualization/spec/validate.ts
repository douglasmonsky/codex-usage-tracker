import { tableRowsForVisualization } from './table';
import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type FlowVisualizationSpecV1,
  type HeatmapVisualizationSpecV1,
  type VisualizationRecord,
  type VisualizationSpecIssue,
  type VisualizationSpecV1,
} from './types';

export function validateVisualizationSpec(spec: VisualizationSpecV1): VisualizationSpecIssue[] {
  const issues: VisualizationSpecIssue[] = [];
  requireValue(issues, 'schema', spec.schema === visualizationSpecSchema, `must equal ${visualizationSpecSchema}`);
  requireText(issues, 'id', spec.id);
  requireText(issues, 'title', spec.title);
  requireText(issues, 'scope.label', spec.scope.label);
  requireText(issues, 'freshness.generatedAt', spec.freshness.generatedAt);
  requireText(issues, 'accessibility.summary', spec.accessibility.summary);
  requireText(issues, 'table.caption', spec.table.caption);
  requireValue(issues, 'table.columns', spec.table.columns.length > 0, 'must include at least one column');

  if (spec.kind === 'cartesian') validateCartesian(spec, issues);
  if (spec.kind === 'heatmap') validateHeatmap(spec, issues);
  if (spec.kind === 'flow') validateFlow(spec, issues);

  const rows = tableRowsForVisualization(spec);
  if (requiresData(spec.state.kind) && rows.length === 0) {
    issues.push({ path: 'data', message: `${spec.state.kind} visualizations must include table-equivalent data` });
  }
  validateTableColumns(spec, rows.map(row => row.values), issues);
  validateInteractionFields(spec, rows.map(row => row.values), issues);
  validateAnnotations(spec, issues);
  return issues;
}

export function assertVisualizationSpec(spec: VisualizationSpecV1): VisualizationSpecV1 {
  const issues = validateVisualizationSpec(spec);
  if (issues.length) {
    throw new Error(`Invalid visualization spec:\n${issues.map(issue => `- ${issue.path}: ${issue.message}`).join('\n')}`);
  }
  return spec;
}

function validateCartesian(spec: CartesianVisualizationSpecV1, issues: VisualizationSpecIssue[]) {
  requireValue(issues, 'series', spec.series.length > 0, 'must include at least one series');
  validateRowsHaveFields(spec.data.rows, [spec.axes.x.field, spec.axes.y.field], 'axes', issues);
  for (const [index, series] of spec.series.entries()) {
    requireText(issues, `series.${index}.id`, series.id);
    requireText(issues, `series.${index}.label`, series.label);
    const fields = [series.xField, series.yField];
    if ((series.lowerField && !series.upperField) || (!series.lowerField && series.upperField)) {
      issues.push({ path: `series.${index}`, message: 'confidence bands require both lowerField and upperField' });
    }
    if (series.lowerField) fields.push(series.lowerField);
    if (series.upperField) fields.push(series.upperField);
    validateRowsHaveFields(spec.data.rows, fields, `series.${index}`, issues);
  }
  const ids = spec.series.map(series => series.id);
  if (new Set(ids).size !== ids.length) issues.push({ path: 'series', message: 'series ids must be unique' });
}

function validateHeatmap(spec: HeatmapVisualizationSpecV1, issues: VisualizationSpecIssue[]) {
  validateRowsHaveFields(
    spec.data.rows,
    [spec.encoding.x.field, spec.encoding.y.field, spec.encoding.value.field],
    'encoding',
    issues,
  );
}

function validateFlow(spec: FlowVisualizationSpecV1, issues: VisualizationSpecIssue[]) {
  const nodeIds = spec.data.nodes.map(node => node.id);
  requireValue(issues, 'data.nodes', nodeIds.length > 0 || !requiresData(spec.state.kind), 'must include nodes');
  if (new Set(nodeIds).size !== nodeIds.length) issues.push({ path: 'data.nodes', message: 'node ids must be unique' });
  const nodeSet = new Set(nodeIds);
  for (const [index, link] of spec.data.links.entries()) {
    if (!nodeSet.has(link.source)) issues.push({ path: `data.links.${index}.source`, message: 'must reference a node id' });
    if (!nodeSet.has(link.target)) issues.push({ path: `data.links.${index}.target`, message: 'must reference a node id' });
    if (!Number.isFinite(link.value) || link.value < 0) {
      issues.push({ path: `data.links.${index}.value`, message: 'must be a non-negative finite number' });
    }
  }
}

function validateTableColumns(
  spec: VisualizationSpecV1,
  rows: VisualizationRecord[],
  issues: VisualizationSpecIssue[],
) {
  const columnFields = spec.table.columns.map(column => column.field);
  if (new Set(columnFields).size !== columnFields.length) {
    issues.push({ path: 'table.columns', message: 'column fields must be unique' });
  }
  validateRowsHaveFields(rows, columnFields, 'table.columns', issues);
  if (spec.table.defaultSort && !columnFields.includes(spec.table.defaultSort.field)) {
    issues.push({ path: 'table.defaultSort.field', message: 'must reference a table column' });
  }
}

function validateInteractionFields(
  spec: VisualizationSpecV1,
  rows: VisualizationRecord[],
  issues: VisualizationSpecIssue[],
) {
  const keyField = spec.interactions?.selection?.keyField;
  if (keyField) validateRowsHaveFields(rows, [keyField], 'interactions.selection', issues);
  const zoom = spec.interactions?.zoom;
  if (zoom?.startPercent !== undefined && (zoom.startPercent < 0 || zoom.startPercent > 100)) {
    issues.push({ path: 'interactions.zoom.startPercent', message: 'must be between 0 and 100' });
  }
  if (zoom?.endPercent !== undefined && (zoom.endPercent < 0 || zoom.endPercent > 100)) {
    issues.push({ path: 'interactions.zoom.endPercent', message: 'must be between 0 and 100' });
  }
}

function validateAnnotations(spec: VisualizationSpecV1, issues: VisualizationSpecIssue[]) {
  const ids = (spec.annotations ?? []).map(annotation => annotation.id);
  if (new Set(ids).size !== ids.length) issues.push({ path: 'annotations', message: 'annotation ids must be unique' });
  for (const [index, annotation] of (spec.annotations ?? []).entries()) {
    if (annotation.kind === 'reference-line' && (!annotation.axis || annotation.value === undefined)) {
      issues.push({ path: `annotations.${index}`, message: 'reference lines require axis and value' });
    }
    if (annotation.kind === 'range' && (!annotation.axis || annotation.start === undefined || annotation.end === undefined)) {
      issues.push({ path: `annotations.${index}`, message: 'ranges require axis, start, and end' });
    }
    if (annotation.kind === 'point' && (annotation.x === undefined || annotation.y === undefined)) {
      issues.push({ path: `annotations.${index}`, message: 'points require x and y' });
    }
  }
}

function validateRowsHaveFields(
  rows: VisualizationRecord[],
  fields: string[],
  path: string,
  issues: VisualizationSpecIssue[],
) {
  if (!rows.length) return;
  const available = new Set(rows.flatMap(row => Object.keys(row)));
  for (const field of fields) {
    if (!available.has(field)) issues.push({ path, message: `field ${field} is not present in the data` });
  }
}

function requireText(issues: VisualizationSpecIssue[], path: string, value: string) {
  requireValue(issues, path, value.trim().length > 0, 'must not be empty');
}

function requireValue(issues: VisualizationSpecIssue[], path: string, condition: boolean, message: string) {
  if (!condition) issues.push({ path, message });
}

function requiresData(state: VisualizationSpecV1['state']['kind']) {
  return state === 'ready' || state === 'partial' || state === 'stale';
}
