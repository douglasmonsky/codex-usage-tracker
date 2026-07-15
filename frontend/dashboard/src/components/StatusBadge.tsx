import type { MetricTone } from '../api/types';
import { useShellI18n } from '../app/i18nContext';

type StatusBadgeProps = {
  label: string;
  tone?: MetricTone;
};

export function StatusBadge({ label, tone = 'neutral' }: StatusBadgeProps) {
  const i18n = useShellI18n();
  return <span className={`status-badge ${tone}`}>{i18n.translateText(label)}</span>;
}
