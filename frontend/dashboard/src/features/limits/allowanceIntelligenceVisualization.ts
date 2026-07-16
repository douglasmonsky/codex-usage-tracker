import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type VisualizationRecord,
  type VisualizationValue,
} from '../../visualization';
import type {
  AllowanceSeriesPayload,
  AllowanceStatusPayload,
  AllowanceWindowKindV2,
} from '../../api/allowanceIntelligenceTypes';
import {
  allowancePlanColor,
  allowancePlanFieldKey,
  allowancePlanLabel,
  allowancePlanMedianColor,
  normalizeAllowancePlanType,
} from './allowancePlanPresentation';

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
  const sortedPoints = supportedWindow
    ? [...history.points].sort((left, right) => Date.parse(left.completed_at) - Date.parse(right.completed_at))
    : [];
  const planTypes = [...new Set(sortedPoints.map(point => normalizeAllowancePlanType(point.plan_type)))];
  const planTransitions = sortedPoints.flatMap((point, index) => {
    if (index === 0) return [];
    const previous = normalizeAllowancePlanType(sortedPoints[index - 1].plan_type);
    const current = normalizeAllowancePlanType(point.plan_type);
    if (previous === current) return [];
    return [{
      id: `plan-transition-${point.cycle_id}`,
      label: `Observed plan changed · ${allowancePlanLabel(previous)} → ${allowancePlanLabel(current)}`,
      kind: 'reference-line' as const,
      axis: 'x' as const,
      value: point.completed_at,
      severity: 'neutral' as const,
    }];
  });
  const rows: VisualizationRecord[] = sortedPoints
      .map(point => {
        const outsideRobustRange = !showFullRange && isOutsideRobustRange(
          point.credits_per_percent,
          robustDomain?.min,
          robustDomain?.max,
        );
        const planType = normalizeAllowancePlanType(point.plan_type);
        const row: Record<string, VisualizationValue> = {
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
          planType,
          planLabel: allowancePlanLabel(planType),
        };
        for (const candidate of planTypes) {
          const fieldKey = allowancePlanFieldKey(candidate);
          const matches = candidate === planType;
          row[`plan_${fieldKey}_capacity`] = matches ? row.chartCreditsPerPercent : null;
          row[`plan_${fieldKey}_median`] = matches ? point.rolling_median : null;
          row[`plan_${fieldKey}_q1`] = matches ? point.rolling_q1 : null;
          row[`plan_${fieldKey}_q3`] = matches ? point.rolling_q3 : null;
        }
        return row;
      });
  const clippedCount = showFullRange ? 0 : history.clipped_point_count ?? 0;
  const title = 'Weekly limit capacity over time';
  const copiedRows = series.quality.copied_rows_excluded;
  const clippedLabel = `${clippedCount} capacity ${clippedCount === 1 ? 'point' : 'points'} outside the robust range; exact values remain in the table.`;
  return {
    schema: visualizationSpecSchema,
    id: 'allowance-capacity-weekly',
    title,
    description: supportedWindow
      ? 'Estimated local credits corresponding to one visible weekly allowance percentage point, summarized with one vote per completed reset window.'
      : 'The five-hour rolling window includes expiry and cannot use the monotonic weekly credits-per-percentage model.',
    state: rows.length >= 1
      ? { kind: 'ready' }
      : {
          kind: 'insufficient-data',
          message: supportedWindow
            ? 'Capacity history begins after a quality-approved reset window completes.'
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
      `Observed subscription plans are shown separately: ${planTypes.map(allowancePlanLabel).join(', ') || 'none available'}. Unknown or mixed plans are never inferred from capacity values.`,
    ],
    accessibility: {
      summary: `${title}. ${rows.length} eligible completed reset windows; ${history.boundaries?.length ?? 0} supported changes; ${clippedCount} points outside the robust display range.`,
      details: [
        'Reset-window points retain exact credits-per-percentage values in the table.',
        'The rolling line and quartile band use the trailing eight eligible reset windows after four are available.',
        'Rolling statistics are calculated independently within each observed subscription plan.',
      ],
      keyboardInstructions: 'Use left and right arrow keys to inspect completed reset windows. Use the range controls above the chart to change scope.',
    },
    table: {
      caption: `${title} evidence`,
      columns: [
        { field: 'completedAt', label: 'Reset window completed', type: 'time', align: 'left' },
        { field: 'creditsPerPercent', label: 'Credits / 1%', type: 'number', unit: 'credits_per_percent', align: 'right' },
        { field: 'planLabel', label: 'Subscription plan', type: 'text', align: 'left', localizeValues: true },
        { field: 'rollingMedian', label: 'Rolling median', type: 'number', unit: 'credits_per_percent', align: 'right' },
        { field: 'rollingQ1', label: 'Rolling Q1', type: 'number', unit: 'credits_per_percent', align: 'right' },
        { field: 'rollingQ3', label: 'Rolling Q3', type: 'number', unit: 'credits_per_percent', align: 'right' },
        { field: 'qualityGrade', label: 'Quality', type: 'text', align: 'left', localizeValues: true },
        { field: 'priceCoverage', label: 'Price coverage', type: 'number', unit: 'ratio', align: 'right' },
      ],
      defaultSort: { field: 'completedAt', direction: 'desc' },
    },
    interactions: {
      selection: { keyField: 'id', labelField: 'completedAt' },
      zoom: { axis: 'x', startPercent: 0, endPercent: 100 },
      brush: { axis: 'x' },
    },
    annotations: [
      ...planTransitions,
      ...(history.boundaries ?? []).map(boundary => ({
        id: boundary.boundary_id,
        label: `Supported capacity change · ${formatCredits(boundary.effect_size.median_before_credits_per_percent)} to ${formatCredits(boundary.effect_size.median_after_credits_per_percent)} credits / 1%`,
        kind: 'reference-line' as const,
        axis: 'x' as const,
        value: boundary.effective_at,
        severity: 'info' as const,
      })),
    ],
    kind: 'cartesian',
    showLegend: false,
    data: { rows },
    axes: {
      x: { field: 'completedAt', label: 'Reset-window completion', type: 'time', unit: 'timestamp' },
      y: {
        field: 'chartCreditsPerPercent',
        label: 'Weekly limit capacity',
        type: 'number',
        unit: 'credits_per_percent',
        min: showFullRange ? undefined : robustDomain?.min ?? undefined,
        max: showFullRange ? undefined : robustDomain?.max ?? undefined,
      },
    },
    series: planSeries(planTypes),
  };
}

function planSeries(planTypes: string[]): CartesianVisualizationSpecV1['series'] {
  const series: CartesianVisualizationSpecV1['series'] = planTypes.flatMap(planType => {
    const fieldKey = allowancePlanFieldKey(planType);
    const label = allowancePlanLabel(planType);
    const observedColor = allowancePlanColor(planType);
    const medianColor = allowancePlanMedianColor(planType);
    return [
      {
        id: `plan-${fieldKey}-capacity`,
        label: `${label} reset-window capacity`,
        mark: 'line' as const,
        xField: 'completedAt',
        yField: `plan_${fieldKey}_capacity`,
        color: observedColor,
        lineWidth: 1.5,
        pointStyle: 'hollow',
        showPoints: true,
      },
      {
        id: `plan-${fieldKey}-median`,
        label: `${label} trailing median`,
        mark: 'line' as const,
        xField: 'completedAt',
        yField: `plan_${fieldKey}_median`,
        color: medianColor,
        lineWidth: 3,
        pointStyle: 'none',
        showPoints: false,
        smooth: false,
      },
    ];
  });
  if (planTypes.length === 1) {
    const planType = planTypes[0];
    const fieldKey = allowancePlanFieldKey(planType);
    series.push({
      id: `plan-${fieldKey}-iqr`,
      label: `${allowancePlanLabel(planType)} interquartile range`,
      mark: 'line',
      xField: 'completedAt',
      yField: `plan_${fieldKey}_median`,
      lowerField: `plan_${fieldKey}_q1`,
      upperField: `plan_${fieldKey}_q3`,
      color: allowancePlanMedianColor(planType),
    });
  }
  return series;
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
