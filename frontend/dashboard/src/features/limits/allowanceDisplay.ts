import type {
  buildAllowanceWorkspace,
  AllowanceTone,
} from './allowanceModel';

export function capacityRatio(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`;
}

export function unexplainedMovement(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : `${Math.round(value * 10) / 10}%`;
}

export function statistic(value: number | null | undefined): string {
  return value === null || value === undefined
    ? 'Not available'
    : value.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

export function intervalStatus(
  workspace: ReturnType<typeof buildAllowanceWorkspace>,
): string {
  const evidence = workspace.candidate?.statistical_evidence;
  const before = evidence?.median_confidence_interval_before_95;
  const after = evidence?.median_confidence_interval_after_95;
  if (before?.available && after?.available) return 'Available for both regimes';
  if (before?.available || after?.available) {
    return 'Available for one regime; the other sample is too small';
  }
  return 'Unavailable at the current sample size';
}

export function gradeTone(grade: string): AllowanceTone {
  if (grade === 'strong_local_evidence') return 'risk';
  if (grade === 'possible_regime_change' || grade === 'inconclusive_other_usage_possible') return 'caution';
  if (grade === 'no_change_detected') return 'positive';
  if (grade === 'counter_noise_likely') return 'context';
  return 'neutral';
}

export function gradeLabel(grade: string): string {
  return grade.replaceAll('_', ' ');
}
