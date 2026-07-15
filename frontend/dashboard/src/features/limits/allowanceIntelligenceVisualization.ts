import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type VisualizationRecord,
} from '../../visualization';
import type {
  AllowanceSeriesPayload,
  AllowanceStatusPayload,
  AllowanceWindowKindV2,
} from '../../api/allowanceIntelligenceTypes';

type CapacityVisualizationOptions = {
  showFullRange?: boolean;
};

export function buildAllowanceIntelligenceVisualization(
  series: AllowanceSeriesPayload,
  _status: AllowanceStatusPayload | undefined,
  windowKind: AllowanceWindowKindV2,
  options: CapacityVisualizationOptions = {},
): CartesianVisualizationSpecV1 {
  const history = series.capacity_history;
  const robustDomain = history.robust_domain;
  const showFullRange = options.showFullRange ?? false;
  const supportedWindow = windowKind === 'weekly' && history.status !== 'unsupported_window_model';
  const rows: VisualizationRecord[] = supportedWindow
    ? [...history.points]
      .sort((left, right) => Date.parse(left.completed_at) - Date.parse(right.completed_at))
      .map(point => {
        const outsideRobustRange = !showFullRange && isOutsideRobustRange(
          point.credits_per_percent,
          robustDomain?.min,
          robustDomain?.max,
        );
        return {
          id: point.cycle_id,
          completedAt: point.completed_at,
          creditsPerPercent: point.credits_per_percent,
          chartCreditsPerPercent: showFullRange
            ? point.credits_per_percent
            : clamp(point.credits_per_percent, robustDomain?.min, robustDomain?.max),
          rollingMedian: point.rolling_median,
          rollingQ1: point.rolling_q1,
          rollingQ3: point.rolling_q3,
          qualityGrade: point.quality_grade,
          priceCoverage: point.price_coverage,
          regimeId: point.regime_id,
          outsideRobustRange,
        };
      })
    : [];
  const clippedCount = showFullRange ? 0 : history.clipped_point_count ?? 0;
  const title = 'Weekly limit capacity over time';
  const copiedRows = series.quality.copied_rows_excluded;
  const clippedLabel = `${clippedCount} capacity ${clippedCount === 1 ? 'point' : 'points'} outside the robust range; exact values remain in the table.`;
  return {
    schema: visualizationSpecSchema,
    id: 'allowance-capacity-weekly',
    title,
    description: supportedWindow
      ? 'Estimated local credits corresponding to one visible weekly allowance percentage point, summarized with one vote per completed cycle.'
      : 'The five-hour rolling window includes expiry and cannot use the monotonic weekly credits-per-percentage model.',
    state: rows.length >= 1
      ? { kind: 'ready' }
      : {
          kind: 'insufficient-data',
          message: supportedWindow
            ? 'Capacity history begins after a quality-approved weekly cycle completes.'
            : 'Five-hour capacity requires a separately validated rolling-decay model.',
          requiredRows: 1,
          availableRows: rows.length,
        },
    scope: {
      label: `Weekly · ${series.requested_range.preset} · ${series.granularity}`,
      rowCount: rows.length,
      historyScope: 'active',
      filters: [],
    },
    freshness: {
      generatedAt: series.generated_at,
      sourceRevision: series.revision ?? 'missing',
    },
    caveats: [
      'Credits per 1% is a personal local calibration proxy, not an official allowance total.',
      ...(clippedCount > 0 ? [clippedLabel] : []),
      `${copiedRows} copied clone rows were excluded from canonical usage.`,
    ],
    accessibility: {
      summary: `${title}. ${rows.length} eligible completed cycles; ${history.boundaries?.length ?? 0} supported changes; ${clippedCount} points outside the robust display range.`,
      details: [
        'Cycle points retain exact credits-per-percentage values in the table.',
        'The rolling line and quartile band use the trailing eight eligible cycles after four cycles are available.',
      ],
      keyboardInstructions: 'Use left and right arrow keys to inspect completed cycles. Use the range controls above the chart to change scope.',
    },
    table: {
      caption: `${title} evidence`,
      columns: [
        { field: 'completedAt', label: 'Cycle completed', type: 'time', align: 'left' },
        { field: 'creditsPerPercent', label: 'Credits / 1%', type: 'number', unit: 'credits_per_percent', align: 'right' },
        { field: 'rollingMedian', label: 'Rolling median', type: 'number', unit: 'credits_per_percent', align: 'right' },
        { field: 'rollingQ1', label: 'Rolling Q1', type: 'number', unit: 'credits_per_percent', align: 'right' },
        { field: 'rollingQ3', label: 'Rolling Q3', type: 'number', unit: 'credits_per_percent', align: 'right' },
        { field: 'qualityGrade', label: 'Quality', type: 'text', align: 'left' },
        { field: 'priceCoverage', label: 'Price coverage', type: 'number', unit: 'ratio', align: 'right' },
      ],
      defaultSort: { field: 'completedAt', direction: 'desc' },
    },
    interactions: {
      selection: { keyField: 'id', labelField: 'completedAt' },
      zoom: { axis: 'x', startPercent: 0, endPercent: 100 },
      brush: { axis: 'x' },
    },
    annotations: (history.boundaries ?? []).map(boundary => ({
      id: boundary.boundary_id,
      label: `Supported capacity change · ${formatCredits(boundary.effect_size.median_before_credits_per_percent)} to ${formatCredits(boundary.effect_size.median_after_credits_per_percent)} credits / 1%`,
      kind: 'reference-line',
      axis: 'x',
      value: boundary.effective_at,
      severity: 'info',
    })),
    kind: 'cartesian',
    data: { rows },
    axes: {
      x: { field: 'completedAt', label: 'Cycle completion', type: 'time', unit: 'timestamp' },
      y: {
        field: 'chartCreditsPerPercent',
        label: 'Weekly limit capacity',
        type: 'number',
        unit: 'credits_per_percent',
        min: showFullRange ? undefined : robustDomain?.min ?? undefined,
        max: showFullRange ? undefined : robustDomain?.max ?? undefined,
      },
    },
    series: [
      {
        id: 'cycle-capacity',
        label: 'Completed cycle capacity',
        mark: 'point',
        xField: 'completedAt',
        yField: 'chartCreditsPerPercent',
        color: '#2f6fed',
      },
      {
        id: 'rolling-median',
        label: 'Trailing 8-cycle median',
        mark: 'line',
        xField: 'completedAt',
        yField: 'rollingMedian',
        color: '#16866b',
        smooth: false,
      },
      {
        id: 'interquartile-band',
        label: 'Trailing interquartile range',
        mark: 'line',
        xField: 'completedAt',
        yField: 'rollingMedian',
        lowerField: 'rollingQ1',
        upperField: 'rollingQ3',
        color: '#7656a8',
      },
    ],
  };
}

function isOutsideRobustRange(
  value: number,
  minimum: number | null | undefined,
  maximum: number | null | undefined,
): boolean {
  return (minimum !== null && minimum !== undefined && value < minimum)
    || (maximum !== null && maximum !== undefined && value > maximum);
}

function clamp(
  value: number,
  minimum: number | null | undefined,
  maximum: number | null | undefined,
): number {
  return Math.min(maximum ?? value, Math.max(minimum ?? value, value));
}

function formatCredits(value: number): string {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 }).format(value);
}
