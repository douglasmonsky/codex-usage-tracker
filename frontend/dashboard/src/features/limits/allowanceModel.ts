import type {
  AllowanceChangeCandidate,
  AllowanceDiagnosticsPayload,
  AllowanceEvidenceGrade,
  AllowanceHistoryPayload,
  AllowanceHistoryRow,
  AllowanceResearchReadiness,
  AllowanceSpan,
  AllowanceWindowKind,
  AllowanceWindowReport,
} from '../../api/allowance';
import type { CallRow, DashboardModel } from '../../api/types';

export type AllowanceTone = 'neutral' | 'positive' | 'caution' | 'risk' | 'context';
export type AllowanceHypothesis = 'decreased' | 'stable';

export type AllowanceEvidencePoint = {
  id: string;
  label: string;
  timestamp: string | null;
  estimate: number;
  low: number | null;
  high: number | null;
  deltaPercent: number | null;
  credits: number | null;
  grade: string;
  plan: string;
  recordId: string | null;
};

export type AllowanceWindowEvidence = {
  kind: AllowanceWindowKind;
  metric: 'capacity_proxy' | 'remaining_percent';
  evidenceGrade: AllowanceEvidenceGrade;
  observationCount: number;
  positiveSpanCount: number;
  resetCount: number;
  missingValueCount: number;
  plan: string;
  limitId: string;
  history: AllowanceHistoryRow[];
  points: AllowanceEvidencePoint[];
};

type AllowanceAnswer = {
  label: string;
  title: string;
  detail: string;
  badge: string;
  tone: AllowanceTone;
};

export type AllowanceWorkspace = {
  live: boolean;
  generatedAt: string;
  includeArchived: boolean;
  weekly: AllowanceWindowEvidence;
  fiveHour: AllowanceWindowEvidence;
  primaryGrade: AllowanceEvidenceGrade;
  answer: AllowanceAnswer;
  candidate: AllowanceChangeCandidate | null;
  readiness: AllowanceResearchReadiness;
  notes: string[];
};

export type HypothesisResult = {
  badge: string;
  title: string;
  detail: string;
  tone: AllowanceTone;
};

export function buildAllowanceWorkspace(
  model: DashboardModel,
  diagnostics?: AllowanceDiagnosticsPayload,
  history?: AllowanceHistoryPayload,
  sourceRevision = '',
): AllowanceWorkspace {
  if (!diagnostics && !history) return fallbackWorkspace(model, sourceRevision);

  const weeklyReport = primaryWindowReport(
    (diagnostics?.windows ?? []).filter(window => window.window_kind === 'weekly'),
  );
  const candidate = bestCandidate(weeklyReport?.change_candidates ?? diagnostics?.change_candidates ?? []);
  const readiness = diagnostics?.summary.research_readiness ?? fallbackReadiness('Detector summary unavailable.');
  const primaryGrade = diagnostics?.summary.primary_evidence_grade ?? 'insufficient_data';
  const weekly = liveWindowEvidence('weekly', diagnostics, history, candidate);
  const fiveHour = liveWindowEvidence('five_hour', diagnostics, history, null);
  return {
    live: true,
    generatedAt: diagnostics?.generated_at || history?.generated_at || sourceRevision || 'loaded-local-snapshot',
    includeArchived: diagnostics?.include_archived ?? history?.include_archived ?? false,
    weekly,
    fiveHour,
    primaryGrade,
    answer: answerForGrade(primaryGrade, candidate, readiness, weekly.positiveSpanCount),
    candidate,
    readiness,
    notes: uniqueStrings([...(diagnostics?.notes ?? []), ...(history?.notes ?? [])]),
  };
}

export function evaluateAllowanceHypothesis(
  workspace: AllowanceWorkspace,
  hypothesis: AllowanceHypothesis,
): HypothesisResult {
  if (workspace.weekly.positiveSpanCount < 2 || workspace.primaryGrade === 'insufficient_data') {
    return {
      badge: 'Insufficient evidence',
      title: 'The loaded weekly history cannot test this claim yet',
      detail: workspace.readiness.reasons[0] ?? 'More positive weekly spans are required before comparing regimes.',
      tone: 'neutral',
    };
  }
  if (hypothesis === 'stable') return stableHypothesisResult(workspace);
  if (workspace.primaryGrade === 'no_change_detected') {
    return {
      badge: 'Not supported',
      title: 'No weekly regime change was detected',
      detail: 'The loaded spans are more consistent with stable local behavior than a lower allowance regime.',
      tone: 'positive',
    };
  }
  if (workspace.primaryGrade === 'inconclusive_other_usage_possible' || workspace.candidate?.outside_usage_possible) {
    return {
      badge: 'Inconclusive',
      title: 'A local shift is plausible, but attribution is unresolved',
      detail: 'Usage outside these local Codex logs could explain enough movement that an allowance change is not isolated.',
      tone: 'caution',
    };
  }
  if (workspace.readiness.ready_for_public_claim) {
    return {
      badge: 'Supported locally',
      title: 'Repeated weekly spans support a lower local capacity regime',
      detail: 'The nonparametric detector meets its local sample, effect-size, and p-value thresholds. This remains local evidence, not an internal ledger result.',
      tone: 'risk',
    };
  }
  return {
    badge: 'Possible change',
    title: 'The direction is consistent, but the sample is not claim-ready',
    detail: workspace.readiness.reasons[0] ?? 'More weekly spans are required on both sides of the candidate split.',
    tone: 'caution',
  };
}

export function allowanceEvidenceCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  return [...model.calls]
    .sort((left, right) => callCredits(right) - callCredits(left) || right.totalTokens - left.totalTokens)
    .slice(0, 20);
}

export function buildFallbackAllowanceExport(workspace: AllowanceWorkspace): Record<string, unknown> {
  return {
    schema: 'codex-usage-tracker-allowance-evidence-export-v1',
    generated_at: workspace.generatedAt,
    privacy_mode: 'strict',
    include_archived: workspace.includeArchived,
    summary: {
      primary_evidence_grade: workspace.primaryGrade,
      weekly_observation_count: workspace.weekly.observationCount,
      five_hour_observation_count: workspace.fiveHour.observationCount,
      positive_span_count: workspace.weekly.positiveSpanCount + workspace.fiveHour.positiveSpanCount,
      research_readiness: workspace.readiness,
    },
    windows: [workspace.weekly, workspace.fiveHour].map(window => ({
      window_kind: window.kind,
      evidence_grade: window.evidenceGrade,
      observation_count: window.observationCount,
      positive_span_count: window.positiveSpanCount,
      points: window.points.map(point => ({
        id: point.id,
        label: point.label,
        timestamp: point.timestamp,
        estimate: point.estimate,
        low: point.low,
        high: point.high,
        deltaPercent: point.deltaPercent,
        credits: point.credits,
        grade: point.grade,
        plan: point.plan,
      })),
    })),
    change_candidates: workspace.candidate ? [workspace.candidate] : [],
    notes: [...workspace.notes, 'Static dashboard fallback; local identifiers omitted.'],
  };
}

function liveWindowEvidence(
  kind: AllowanceWindowKind,
  diagnostics: AllowanceDiagnosticsPayload | undefined,
  history: AllowanceHistoryPayload | undefined,
  candidate: AllowanceChangeCandidate | null,
): AllowanceWindowEvidence {
  const reports = (diagnostics?.windows ?? []).filter(window => window.window_kind === kind);
  const report = primaryWindowReport(reports);
  const rows = (history?.rows ?? [])
    .filter(row => row.window_kind === kind && matchesWindow(row, report))
    .sort(historySort);
  const spans = (report?.spans ?? diagnostics?.spans ?? [])
    .filter(span => span.window_kind === kind && matchesWindow(span, report))
    .sort(spanSort);
  const capacityPoints = kind === 'weekly' ? spans.flatMap((span, index) => spanPoint(span, index, report, candidate)) : [];
  const points = capacityPoints.length ? capacityPoints : rows.flatMap((row, index) => historyPoint(row, index, report));
  return {
    kind,
    metric: capacityPoints.length ? 'capacity_proxy' : 'remaining_percent',
    evidenceGrade: report?.evidence_grade ?? (kind === 'five_hour' && rows.length ? 'counter_noise_likely' : 'insufficient_data'),
    observationCount: report?.observation_count ?? rows.length,
    positiveSpanCount: report?.positive_span_count ?? spans.length,
    resetCount: report?.span_stats.reset_or_negative_delta_rows ?? countResets(rows),
    missingValueCount: report?.span_stats.missing_used_percent_rows ?? rows.filter(row => row.used_percent === null).length,
    plan: report?.plan_type ?? rows.find(row => row.plan_type)?.plan_type ?? 'unknown',
    limitId: report?.limit_id ?? rows.find(row => row.limit_id)?.limit_id ?? 'unknown',
    history: rows,
    points,
  };
}

function spanPoint(
  span: AllowanceSpan,
  index: number,
  report: AllowanceWindowReport | undefined,
  candidate: AllowanceChangeCandidate | null,
): AllowanceEvidencePoint[] {
  if (span.credits_per_percent === null) return [];
  const timestamp = span.end_observed_at ?? span.end_observed_date ?? null;
  const interval = candidateInterval(candidate, timestamp);
  return [{
    id: span.record_id || `weekly-span-${index}`,
    label: displayDate(timestamp, `Span ${index + 1}`),
    timestamp,
    estimate: span.credits_per_percent * 100,
    low: interval?.low === null || interval?.low === undefined ? null : interval.low * 100,
    high: interval?.high === null || interval?.high === undefined ? null : interval.high * 100,
    deltaPercent: span.delta_usage_percent,
    credits: span.estimated_usage_credits,
    grade: report?.evidence_grade ?? 'insufficient_data',
    plan: span.plan_type ?? report?.plan_type ?? 'unknown',
    recordId: span.record_id ?? null,
  }];
}

function historyPoint(
  row: AllowanceHistoryRow,
  index: number,
  report: AllowanceWindowReport | undefined,
): AllowanceEvidencePoint[] {
  if (row.remaining_percent === null) return [];
  return [{
    id: row.record_id || `${row.window_kind}-observation-${index}`,
    label: displayDate(row.observed_at ?? row.observed_date, `Observation ${index + 1}`),
    timestamp: row.observed_at ?? row.observed_date,
    estimate: row.remaining_percent,
    low: null,
    high: null,
    deltaPercent: row.used_percent,
    credits: row.usage_credits,
    grade: report?.evidence_grade ?? (row.window_kind === 'five_hour' ? 'counter_noise_likely' : 'insufficient_data'),
    plan: row.plan_type ?? report?.plan_type ?? 'unknown',
    recordId: row.record_id ?? null,
  }];
}

function fallbackWorkspace(model: DashboardModel, sourceRevision: string): AllowanceWorkspace {
  const weeklyPoints = [...model.weeklyWindows].reverse().map((window, index) => ({
    id: `loaded-week-${index}`,
    label: window.week,
    timestamp: null,
    estimate: window.projected,
    low: null,
    high: null,
    deltaPercent: window.observedPct,
    credits: window.credits,
    grade: window.confidence.toLowerCase(),
    plan: window.plan,
    recordId: null,
  }));
  const fiveHourPoints: AllowanceEvidencePoint[] = [];
  const readiness = fallbackReadiness('Live allowance diagnostics are required before testing a change claim.');
  const weekly = fallbackWindow('weekly', 'capacity_proxy', weeklyPoints, model.weeklyWindows.length);
  const fiveHour = fallbackWindow('five_hour', 'remaining_percent', fiveHourPoints, fiveHourPoints.length);
  return {
    live: false,
    generatedAt: sourceRevision || 'loaded-aggregate-snapshot',
    includeArchived: false,
    weekly,
    fiveHour,
    primaryGrade: 'insufficient_data',
    answer: answer(
      'Evidence status',
      'Live allowance detector unavailable in this static snapshot',
      'Projected weekly windows remain visible for orientation, but only the localhost detector can compare normalized positive spans and candidate regimes.',
      'Descriptive fallback',
      'context',
    ),
    candidate: null,
    readiness,
    notes: ['Loaded aggregate projections are descriptive fallback data, not detector output.'],
  };
}

function fallbackWindow(
  kind: AllowanceWindowKind,
  metric: AllowanceWindowEvidence['metric'],
  points: AllowanceEvidencePoint[],
  observationCount: number,
): AllowanceWindowEvidence {
  return {
    kind,
    metric,
    evidenceGrade: kind === 'five_hour' ? 'counter_noise_likely' : 'insufficient_data',
    observationCount,
    positiveSpanCount: 0,
    resetCount: 0,
    missingValueCount: 0,
    plan: points[0]?.plan ?? 'unknown',
    limitId: 'loaded-aggregate',
    history: [],
    points,
  };
}

function answerForGrade(
  grade: AllowanceEvidenceGrade,
  candidate: AllowanceChangeCandidate | null,
  readiness: AllowanceResearchReadiness,
  spanCount: number,
): AllowanceAnswer {
  if (grade === 'no_change_detected') return answer('Current result', 'No weekly regime change detected', 'The loaded positive spans remain within one local regime.', 'No change detected', 'positive');
  if (grade === 'counter_noise_likely') return answer('Current result', 'The 5-hour counter is behaving like a noisy rolling window', 'Use weekly spans as the primary signal before drawing a limit conclusion.', 'Counter noise likely', 'context');
  if (grade === 'inconclusive_other_usage_possible') return answer('Current result', 'Observed movement is not fully attributable to these local logs', 'Outside usage remains plausible, so the detector cannot isolate an allowance change.', 'Inconclusive', 'caution');
  if (grade === 'possible_regime_change') return answer('Candidate regime change', candidateSummary(candidate), 'The direction is consistent, but repeated weekly evidence is still below the public-claim threshold.', 'Possible change', 'caution');
  if (grade === 'strong_local_evidence') return answer('Candidate regime change', candidateSummary(candidate), readiness.ready_for_public_claim ? 'Local sample, effect-size, and p-value thresholds are met. This is still not an OpenAI ledger result.' : 'The local shift is strong, but at least one research-readiness requirement remains unmet.', readiness.ready_for_public_claim ? 'Claim-ready locally' : 'Strong local evidence', 'risk');
  return answer('Evidence status', 'Not enough weekly evidence to test an allowance change', `${spanCount} positive weekly spans are loaded. More observations are needed before comparing regimes.`, 'Insufficient data', 'neutral');
}

function stableHypothesisResult(workspace: AllowanceWorkspace): HypothesisResult {
  if (workspace.primaryGrade === 'no_change_detected') return { badge: 'Consistent', title: 'Stable weekly behavior fits the loaded evidence', detail: 'No candidate split cleared the detector thresholds.', tone: 'positive' };
  if (workspace.primaryGrade === 'inconclusive_other_usage_possible') return { badge: 'Inconclusive', title: 'Stable behavior cannot be isolated either', detail: 'Outside usage and unexplained movement weaken both the stable and decreased hypotheses.', tone: 'caution' };
  return { badge: 'Not supported', title: 'A candidate weekly shift conflicts with the stable hypothesis', detail: 'Review the candidate split and readiness criteria before deciding whether the shift is durable.', tone: 'risk' };
}

function answer(label: string, title: string, detail: string, badge: string, tone: AllowanceTone): AllowanceAnswer {
  return { label, title, detail, badge, tone };
}

function candidateSummary(candidate: AllowanceChangeCandidate | null): string {
  const ratio = candidate?.capacity_ratio;
  const date = displayDate(candidate?.candidate_start_observed_at ?? null, 'the candidate split');
  return ratio === null || ratio === undefined
    ? `Weekly behavior shifted around ${date}`
    : `The recent local capacity proxy is ${Math.round(ratio * 100)}% of the earlier regime after ${date}`;
}

function candidateInterval(candidate: AllowanceChangeCandidate | null, timestamp: string | null) {
  if (!candidate || !timestamp) return null;
  const recent = Date.parse(timestamp) >= Date.parse(candidate.candidate_start_observed_at ?? 'invalid');
  return recent
    ? candidate.statistical_evidence.median_confidence_interval_after_95
    : candidate.statistical_evidence.median_confidence_interval_before_95;
}

function primaryWindowReport(reports: AllowanceWindowReport[]): AllowanceWindowReport | undefined {
  return [...reports].sort((left, right) => right.positive_span_count - left.positive_span_count || right.observation_count - left.observation_count)[0];
}

function matchesWindow(
  row: Pick<AllowanceHistoryRow | AllowanceSpan, 'plan_type' | 'limit_id'>,
  report: AllowanceWindowReport | undefined,
): boolean {
  if (!report) return true;
  return (row.plan_type ?? null) === report.plan_type && (row.limit_id ?? null) === report.limit_id;
}

function bestCandidate(candidates: AllowanceChangeCandidate[]): AllowanceChangeCandidate | null {
  return [...candidates].sort((left, right) => Number(right.statistical_evidence.public_claim_ready) - Number(left.statistical_evidence.public_claim_ready) || (left.capacity_ratio ?? 1) - (right.capacity_ratio ?? 1))[0] ?? null;
}

function fallbackReadiness(reason: string): AllowanceResearchReadiness {
  return {
    detector_version: 'nonparametric-v1',
    ready_for_public_claim: false,
    weekly_positive_span_count: 0,
    minimum_split_spans_for_public_claim: 6,
    p_value_threshold_for_public_claim: 0.05,
    best_candidate_capacity_ratio: null,
    reasons: [reason],
  };
}

function historySort(left: AllowanceHistoryRow, right: AllowanceHistoryRow): number {
  return Date.parse(right.observed_at ?? '') - Date.parse(left.observed_at ?? '');
}

function spanSort(left: AllowanceSpan, right: AllowanceSpan): number {
  return Date.parse(right.end_observed_at ?? right.end_observed_date ?? '')
    - Date.parse(left.end_observed_at ?? left.end_observed_date ?? '');
}

function countResets(rows: AllowanceHistoryRow[]): number {
  return rows.slice(1).filter((row, index) => row.used_percent !== null && rows[index].used_percent !== null && row.used_percent < (rows[index].used_percent ?? 0)).length;
}

function displayDate(value: string | null, fallback: string): string {
  if (!value) return fallback;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}

function callCredits(call: CallRow): number {
  return call.credits > 0 ? call.credits : call.cost * 25;
}
