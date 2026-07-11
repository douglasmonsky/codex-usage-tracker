import { MetricReadout, Surface } from '../../design';
import { formatCompact, formatNumber, pct } from '../shared/format';
import type { OverviewLoadedMetrics } from './overviewModel';
import styles from './OverviewPage.module.css';

export function OverviewMetrics({ metrics, availableCalls }: { metrics: OverviewLoadedMetrics; availableCalls: number }) {
  const tokenDetail = [
    `cached ${formatCompact(metrics.cachedInputTokens)}`,
    `uncached ${formatCompact(metrics.uncachedInputTokens)}`,
    `output ${formatCompact(metrics.outputTokens)}`,
    `reasoning ${formatCompact(metrics.reasoningOutputTokens)}`,
  ].join(' / ');
  return (
    <div className={styles.metricGrid} aria-label="Loaded usage metrics">
      <Surface><MetricReadout label="Calls loaded" value={formatNumber(metrics.calls)} detail={`${formatNumber(availableCalls)} available in scope`} /></Surface>
      <Surface><MetricReadout label="Total tokens" value={formatCompact(metrics.totalTokens)} detail={tokenDetail} /></Surface>
      <Surface><MetricReadout label="Cache reuse" value={pct(metrics.cachePercent)} detail={`${formatCompact(metrics.cachedInputTokens)} cached input tokens`} /></Surface>
      <Surface><MetricReadout label="Estimated credits" value={metrics.estimatedCredits.toFixed(1)} detail="Loaded calls with mapped credit rates" /></Surface>
    </div>
  );
}
