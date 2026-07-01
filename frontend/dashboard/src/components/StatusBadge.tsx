import type { MetricTone } from '../api/types';

type StatusBadgeProps = {
  label: string;
  tone?: MetricTone;
};

export function StatusBadge({ label, tone = 'neutral' }: StatusBadgeProps) {
  return <span className={`status-badge ${tone}`}>{label}</span>;
}
