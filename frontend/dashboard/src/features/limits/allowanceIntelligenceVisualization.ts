import type {
  AllowanceSeriesPayload,
  AllowanceStatusPayload,
  AllowanceWindowKindV2,
} from '../../api/types';
import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type VisualizationRecord,
} from '../../visualization';

export function buildAllowanceIntelligenceVisualization(
  series: AllowanceSeriesPayload,
  status: AllowanceStatusPayload | undefined,
  windowKind: AllowanceWindowKindV2,
): CartesianVisualizationSpecV1 {
  const rows: VisualizationRecord[] = [...series.points]
    .sort((left, right) => Date.parse(left.observed_at) - Date.parse(right.observed_at))
    .map(point => ({
      id: `${point.cycle_id}:${point.observed_at}:${point.kind}`,
      observedAt: point.observed_at,
      observed: point.kind === 'observed' ? point.used_percent ?? null : null,
      reconstructed: null,
      forecast: null,
      forecastLow: null,
      forecastHigh: null,
      pointKind: point.kind,
      cycleId: point.cycle_id,
    }));
  const estimation = windowKind === 'weekly' ? status?.estimation : undefined;
  const reconstructed = estimation?.weekly_estimate.used_percent;
  const forecast = estimation?.forecast;
  if (reconstructed !== null && reconstructed !== undefined) {
    rows.push({
      id: 'current-reconstruction',
      observedAt: status?.generated_at ?? series.generated_at,
      observed: null,
      reconstructed,
      forecast: forecast?.used_percent ?? null,
      forecastLow: forecast?.quantiles?.p10 ?? null,
      forecastHigh: forecast?.quantiles?.p90 ?? null,
      pointKind: forecast?.used_percent === null || forecast?.used_percent === undefined ? 'estimated' : 'forecast',
      cycleId: status?.weekly?.cohort_id ?? 'weekly',
    });
  }
  const title = windowKind === 'weekly' ? 'Weekly usage over time' : '5-hour observed usage';
  const seriesSpecs: CartesianVisualizationSpecV1['series'] = [{
    id: 'observed',
    label: 'Observed usage',
    mark: 'line',
    xField: 'observedAt',
    yField: 'observed',
    color: '#16866b',
    smooth: false,
  }];
  if (reconstructed !== null && reconstructed !== undefined) {
    seriesSpecs.push({
      id: 'reconstructed',
      label: 'Reconstructed current use',
      mark: 'point',
      xField: 'observedAt',
      yField: 'reconstructed',
      color: '#2f6fed',
    });
  }
  if (forecast?.used_percent !== null && forecast?.used_percent !== undefined && forecast.quantiles) {
    seriesSpecs.push({
      id: 'validated-forecast',
      label: 'Validated estimate interval',
      mark: 'point',
      xField: 'observedAt',
      yField: 'forecast',
      lowerField: 'forecastLow',
      upperField: 'forecastHigh',
      color: '#7656a8',
    });
  }
  return {
    schema: visualizationSpecSchema,
    id: `allowance-intelligence-${windowKind.replace('_', '-')}`,
    title,
    description: windowKind === 'weekly'
      ? 'Observed weekly percentage used, with separately labeled personal reconstruction and validated interval when available.'
      : 'Observed 5-hour rolling-window usage. Resets break the observed sequence.',
    state: rows.length >= 2
      ? { kind: 'ready' }
      : { kind: 'insufficient-data', message: 'At least two allowance observations are required.', requiredRows: 2, availableRows: rows.length },
    scope: {
      label: `${windowKind === 'weekly' ? 'Weekly' : '5-hour'} · ${series.requested_range.preset} · ${series.granularity}`,
      rowCount: rows.length,
      historyScope: 'active',
      filters: [],
    },
    freshness: {
      generatedAt: series.generated_at,
      sourceRevision: series.revision ?? 'missing',
    },
    caveats: [
      'Observed percentages come from local Codex rate-limit snapshots.',
      'Reconstructed and forecast values use personal priced-usage history and are never official allowance values.',
      `${series.quality.copied_rows_excluded} copied clone rows were excluded from canonical usage.`,
    ],
    accessibility: {
      summary: `${title}. ${series.points.length} source points; ${series.cycles.length} cycles. Observed and estimated values are separate series.`,
      details: ['Reset rows interrupt the observed sequence.', 'Switch to table view for exact values and point kinds.'],
      keyboardInstructions: 'Use left and right arrow keys to inspect points. Use the range and granularity controls above the chart to change scope.',
    },
    table: {
      caption: `${title} evidence`,
      columns: [
        { field: 'observedAt', label: 'Observed at', type: 'time', align: 'left' },
        { field: 'observed', label: 'Observed used', type: 'number', unit: 'percent', align: 'right' },
        { field: 'reconstructed', label: 'Reconstructed used', type: 'number', unit: 'percent', align: 'right' },
        { field: 'forecastLow', label: 'Validated low', type: 'number', unit: 'percent', align: 'right' },
        { field: 'forecastHigh', label: 'Validated high', type: 'number', unit: 'percent', align: 'right' },
        { field: 'pointKind', label: 'Point kind', type: 'text', align: 'left' },
      ],
      defaultSort: { field: 'observedAt', direction: 'desc' },
    },
    interactions: {
      selection: { keyField: 'id', labelField: 'observedAt' },
      zoom: { axis: 'x', startPercent: 0, endPercent: 100 },
      brush: { axis: 'x' },
    },
    annotations: [],
    kind: 'cartesian',
    data: { rows },
    axes: {
      x: { field: 'observedAt', label: 'Observed time', type: 'time', unit: 'timestamp' },
      y: { field: 'observed', label: 'Allowance used', type: 'number', unit: 'percent', min: 0, max: 100 },
    },
    series: seriesSpecs,
  };
}
