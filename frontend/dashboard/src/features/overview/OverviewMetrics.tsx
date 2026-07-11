import { MetricReadout, Surface } from '../../design';
import { formatCompact, formatNumber, pct } from '../shared/format';
import type { OverviewLoadedMetrics } from './overviewModel';
import styles from './OverviewPage.module.css';

type OverviewMetricsProps = {
  metrics: OverviewLoadedMetrics;
  loadedCalls: number;
  availableCalls: number;
};

export function OverviewMetrics({ metrics, loadedCalls, availableCalls }: OverviewMetricsProps) {
  const scopeMetrics = metrics.basis === 'scope';
  const tokenDetail = [
    `cached ${formatCompact(metrics.cachedInputTokens)}`,
    `uncached ${formatCompact(metrics.uncachedInputTokens)}`,
    `output ${formatCompact(metrics.outputTokens)}`,
    `reasoning ${formatCompact(metrics.reasoningOutputTokens)}`,
  ].join(' / ');
  return (
    <div className={styles.metricGrid} aria-label={scopeMetrics ? 'Selected scope usage metrics' : 'Loaded usage metrics'}>
      <Surface>
        <MetricReadout
          label={scopeMetrics ? 'Calls in scope' : 'Calls loaded'}
          value={formatNumber(metrics.calls)}
          detail={scopeMetrics ? `${formatNumber(loadedCalls)} evidence rows loaded` : `${formatNumber(availableCalls)} available in scope`}
        />
      </Surface>
      <Surface><MetricReadout label="Total tokens" value={formatCompact(metrics.totalTokens)} detail={tokenDetail} /></Surface>
      <Surface><MetricReadout label="Cache reuse" value={pct(metrics.cachePercent)} detail={`${formatCompact(metrics.cachedInputTokens)} cached input tokens`} /></Surface>
      <Surface><MetricReadout label="Estimated credits" value={metrics.estimatedCredits.toFixed(1)} detail={scopeMetrics ? 'Selected scope with mapped credit rates' : 'Loaded calls with mapped credit rates'} /></Surface>
    </div>
  );
}
