import type { MetricCard as MetricCardModel } from '../../api/types';
import { MetricCard } from '../../components/MetricCard';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import type { OverviewLoadedMetrics } from './overviewModel';
import styles from './OverviewPage.module.css';

type OverviewMetricsProps = {
  metrics: OverviewLoadedMetrics;
  loadedCalls: number;
  availableCalls: number;
};

const creditFormat = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function OverviewMetrics({ metrics, loadedCalls, availableCalls }: OverviewMetricsProps) {
  const scopeMetrics = metrics.basis === 'scope';
  const cards: MetricCardModel[] = [
    {
      label: 'Total Calls',
      value: formatNumber(metrics.calls),
      trend: scopeMetrics ? 'complete selected scope' : 'loaded evidence rows',
      detail: scopeMetrics
        ? `${formatNumber(loadedCalls)} detailed rows available`
        : `${formatNumber(availableCalls)} calls available in scope`,
      tone: 'blue',
    },
    {
      label: 'Total Tokens',
      value: formatCompact(metrics.totalTokens),
      trend: `${formatCompact(metrics.cachedInputTokens)} cached input`,
      detail: 'reported token accounting',
      tone: 'purple',
      breakdown: [
        { label: 'Cached', value: formatCompact(metrics.cachedInputTokens) },
        { label: 'Uncached', value: formatCompact(metrics.uncachedInputTokens) },
        { label: 'Output', value: formatCompact(metrics.outputTokens) },
        { label: 'Reasoning', value: formatCompact(metrics.reasoningOutputTokens) },
      ],
    },
    {
      label: 'Cache Reuse',
      value: metrics.hasInputTokens ? pct(metrics.cachePercent) : 'No input data',
      trend: metrics.hasInputTokens
        ? metrics.cachePercent >= 80 ? 'healthy cache reuse' : 'risk: low cache reuse'
        : 'cache reuse unavailable',
      detail: metrics.hasInputTokens
        ? `${formatCompact(metrics.cachedInputTokens)} cached input tokens`
        : 'No reported input tokens in this scope',
      tone: metrics.hasInputTokens ? metrics.cachePercent >= 80 ? 'green' : 'orange' : 'blue',
    },
    {
      label: 'Estimated Cost',
      value: metrics.hasPricingCoverage ? money(metrics.estimatedCostUsd) : 'Unavailable',
      trend: metrics.hasPricingCoverage
        ? scopeMetrics ? 'complete selected scope' : 'loaded calls only'
        : 'pricing coverage unavailable',
      detail: metrics.hasPricingCoverage
        ? 'calls with mapped cost and credit rates'
        : 'No loaded calls have mapped cost rates',
      tone: metrics.hasPricingCoverage ? 'orange' : 'blue',
      breakdown: metrics.hasPricingCoverage
        ? [{ label: 'Estimated credits', value: creditFormat.format(metrics.estimatedCredits) }]
        : undefined,
    },
  ];
  return (
    <section className={styles.metricGrid} aria-label={scopeMetrics ? 'Selected scope usage metrics' : 'Loaded usage metrics'}>
      {cards.map(card => <MetricCard key={card.label} card={card} showAnnotations={false} />)}
    </section>
  );
}
