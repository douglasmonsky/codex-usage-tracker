import type {
  AllowanceChangeCandidate,
  AllowanceHistoryRow,
  AllowanceWindowKind,
} from '../../api/allowance';
import {
  visualizationSpecSchema,
  type CartesianVisualizationSpecV1,
  type VisualizationAnnotation,
  type VisualizationRecord,
} from '../../visualization';
import type {
  AllowanceEvidencePoint,
  AllowanceWindowEvidence,
  AllowanceWorkspace,
} from './allowanceModel';

export function buildAllowanceVisualizationSpec(
  workspace: AllowanceWorkspace,
  kind: AllowanceWindowKind,
): CartesianVisualizationSpecV1 {
  const window = kind === 'weekly' ? workspace.weekly : workspace.fiveHour;
  const capacityMetric = window.metric === 'capacity_proxy';
  const rows = window.points.map(point => visualizationRow(point));
  const values = window.points.flatMap(point => [point.estimate, point.low, point.high]).filter(isNumber);
  const ready = rows.length >= 2;
  const hasIntervals = window.points.some(point => point.low !== null && point.high !== null);
  const xType = window.points.every(point => point.timestamp && Number.isFinite(Date.parse(point.timestamp)))
    ? 'time'
    : 'category';
  const recentPointCount = Math.min(12, rows.length);
  const startPercent = rows.length > recentPointCount ? Math.round(100 - (recentPointCount / rows.length) * 100) : 0;
  const title = capacityMetric
    ? 'Weekly local capacity evidence'
    : kind === 'weekly' ? 'Observed weekly remaining' : '5-hour rolling context';
  const metricLabel = capacityMetric ? 'Capacity proxy' : 'Remaining';
  const unit = capacityMetric ? 'credits' : 'percent';
  const annotations = buildAllowanceAnnotations(window, kind === 'weekly' ? workspace.candidate : null);

  return {
    schema: visualizationSpecSchema,
    id: `allowance-${kind.replace('_', '-')}`,
    title,
    description: capacityMetric
      ? workspace.live
        ? 'Estimated credits per 100 percentage points of observed weekly movement, with exact median intervals when the sample supports them.'
        : 'Loaded aggregate weekly projections for orientation. Exact detector intervals require the localhost allowance endpoints.'
      : 'Observed percentage remaining. The 5-hour view is intentionally secondary because rolling-window movement is noisy.',
    state: ready
      ? { kind: 'ready' }
      : {
          kind: 'insufficient-data',
          message: `At least two ${kind === 'weekly' ? 'weekly spans' : 'observations'} are required for a trend.`,
          requiredRows: 2,
          availableRows: rows.length,
        },
    scope: {
      label: `${window.plan} · ${kind === 'weekly' ? 'weekly primary signal' : 'secondary rolling-window context'}`,
      rowCount: rows.length,
      historyScope: workspace.includeArchived ? 'all' : 'active',
      filters: [window.limitId],
    },
    freshness: {
      generatedAt: workspace.generatedAt || 'loaded-local-snapshot',
      sourceRevision: workspace.readiness.detector_version,
    },
    caveats: capacityMetric
      ? ['This is a local capacity proxy, not an official OpenAI allowance or billing ledger.', ...workspace.notes]
      : ['Rolling-window movement, resets, and sparse observations make the 5-hour counter noisy.', ...workspace.notes],
    accessibility: {
      summary: chartSummary(workspace, window, kind),
      details: annotationDetails(annotations),
      keyboardInstructions: 'Use left and right arrow keys to move through observations. Switch to the table for exact values.',
    },
    table: {
      caption: `${title} evidence`,
      columns: [
        { field: 'window', label: 'Observed', type: xType, align: 'left' },
        { field: 'estimate', label: metricLabel, type: 'number', unit, align: 'right' },
        ...(capacityMetric && hasIntervals ? [
          { field: 'low', label: '95% low', type: 'number' as const, unit: 'credits' as const, align: 'right' as const },
          { field: 'high', label: '95% high', type: 'number' as const, unit: 'credits' as const, align: 'right' as const },
        ] : []),
        ...(capacityMetric ? [
          { field: 'deltaPercent', label: 'Observed movement', type: 'number' as const, unit: 'percent' as const, align: 'right' as const },
          { field: 'credits', label: 'Estimated credits', type: 'number' as const, unit: 'credits' as const, align: 'right' as const },
        ] : []),
        { field: 'grade', label: 'Evidence grade', type: 'text', align: 'left' },
      ],
      defaultSort: { field: 'window', direction: 'asc' },
    },
    interactions: {
      selection: { keyField: 'id', labelField: 'window' },
      zoom: { axis: 'x', startPercent, endPercent: 100 },
      brush: { axis: 'x' },
    },
    annotations,
    kind: 'cartesian',
    data: { rows },
    axes: {
      x: { field: 'window', label: kind === 'weekly' ? 'Weekly evidence span' : 'Observed time', type: xType, unit: xType === 'time' ? 'timestamp' : undefined },
      y: {
        field: 'estimate',
        label: capacityMetric ? 'Credits per 100% observed movement' : 'Percent remaining',
        type: 'number',
        unit,
        min: capacityMetric ? roundedAxisMinimum(values) : 0,
        max: capacityMetric ? roundedAxisMaximum(values) : 100,
      },
    },
    series: [{
      id: capacityMetric ? 'capacity-proxy' : 'remaining-percent',
      label: capacityMetric ? 'Local capacity proxy' : kind === 'weekly' ? 'Weekly remaining' : 'Noisy 5-hour remaining',
      mark: 'line',
      xField: 'window',
      yField: 'estimate',
      ...(hasIntervals ? { lowerField: 'low', upperField: 'high' } : {}),
      color: capacityMetric ? '#2f6fed' : kind === 'weekly' ? '#16866b' : '#9a5900',
      smooth: false,
    }],
  };
}

function buildAllowanceAnnotations(
  window: AllowanceWindowEvidence,
  candidate: AllowanceChangeCandidate | null,
): VisualizationAnnotation[] {
  const annotations: VisualizationAnnotation[] = [];
  if (candidate?.candidate_start_observed_at) {
    annotations.push({
      id: 'candidate-regime-shift',
      label: candidate.outside_usage_possible ? 'Candidate shift · outside usage possible' : 'Candidate weekly regime shift',
      kind: 'reference-line',
      axis: 'x',
      value: candidate.candidate_start_observed_at,
      severity: candidate.statistical_evidence.public_claim_ready ? 'critical' : 'warning',
      evidenceKeys: window.points.filter(point => point.recordId).map(point => point.id),
    });
  }
  annotations.push(...resetAnnotations(window.history).slice(-4));
  annotations.push(...gapAnnotations(window.history, window.kind).slice(-4));
  return annotations;
}

function visualizationRow(point: AllowanceEvidencePoint): VisualizationRecord {
  return {
    id: point.id,
    window: point.timestamp ?? point.label,
    estimate: round(point.estimate),
    low: point.low === null ? null : round(point.low),
    high: point.high === null ? null : round(point.high),
    deltaPercent: point.deltaPercent === null ? null : round(point.deltaPercent),
    credits: point.credits === null ? null : round(point.credits),
    grade: point.grade,
    plan: point.plan,
  };
}

function resetAnnotations(rows: AllowanceHistoryRow[]): VisualizationAnnotation[] {
  return rows.slice(1).flatMap((row, index) => {
    const previous = rows[index];
    if (row.used_percent === null || previous.used_percent === null || row.used_percent >= previous.used_percent || !row.observed_at) return [];
    return [{
      id: `allowance-reset-${index}`,
      label: 'Observed counter reset or rollback',
      kind: 'reference-line' as const,
      axis: 'x' as const,
      value: row.observed_at,
      severity: 'info' as const,
      evidenceKeys: row.record_id ? [row.record_id] : undefined,
    }];
  });
}

function gapAnnotations(rows: AllowanceHistoryRow[], kind: AllowanceWindowKind): VisualizationAnnotation[] {
  const threshold = (kind === 'weekly' ? 48 : 8) * 60 * 60 * 1000;
  return rows.slice(1).flatMap((row, index) => {
    const previous = rows[index];
    const start = Date.parse(previous.observed_at ?? '');
    const end = Date.parse(row.observed_at ?? '');
    if (!Number.isFinite(start) || !Number.isFinite(end) || end - start <= threshold) return [];
    return [{
      id: `allowance-gap-${index}`,
      label: 'Observation gap',
      kind: 'range' as const,
      axis: 'x' as const,
      start: previous.observed_at,
      end: row.observed_at,
      severity: 'neutral' as const,
    }];
  });
}

function chartSummary(
  workspace: AllowanceWorkspace,
  window: AllowanceWindowEvidence,
  kind: AllowanceWindowKind,
): string {
  if (window.points.length < 2) return `Only ${window.points.length} usable ${kind === 'weekly' ? 'weekly span' : 'observation'} is available.`;
  if (kind === 'five_hour') return `${window.points.length} 5-hour observations are shown as noisy rolling-window context, not primary allowance evidence.`;
  return workspace.answer.detail;
}

function annotationDetails(annotations: VisualizationAnnotation[]): string[] | undefined {
  const details = [...new Set(annotations.map(annotation => annotation.label))];
  return details.length ? details : undefined;
}

function roundedAxisMinimum(values: number[]): number {
  if (!values.length) return 0;
  return Math.max(0, Math.floor(Math.min(...values) * 0.9));
}

function roundedAxisMaximum(values: number[]): number {
  if (!values.length) return 1;
  return Math.max(1, Math.ceil(Math.max(...values) * 1.1));
}

function isNumber(value: number | null): value is number {
  return value !== null && Number.isFinite(value);
}

function round(value: number): number {
  return Math.round(value * 100) / 100;
}
