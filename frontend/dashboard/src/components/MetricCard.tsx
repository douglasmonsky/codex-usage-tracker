import { Activity, CircleDollarSign, Database, Gauge, PhoneCall, type LucideIcon } from 'lucide-react';

import type { MetricCard as MetricCardModel } from '../api/types';
import { useShellI18n } from '../app/i18nContext';

const iconByLabel: Record<string, LucideIcon> = {
  'Cache Hit Rate': Database,
  'Cache Reuse': Database,
  'Estimated Cost': CircleDollarSign,
  'Estimated Credits': CircleDollarSign,
  'Total Calls': PhoneCall,
  'Total Tokens': Activity,
  'Usage Remaining': Gauge,
};

export function MetricCard({
  card,
  showAnnotations = true,
}: {
  card: MetricCardModel;
  showAnnotations?: boolean;
}) {
  const i18n = useShellI18n();
  const Icon = iconByLabel[card.label] ?? Activity;
  const trendTone = card.trend.startsWith('down') || card.trend.includes('risk') ? 'negative' : 'positive';

  return (
    <article className={`metric-card metric-card-${card.tone}`}>
      <div className="metric-icon" aria-hidden="true">
        <Icon size={22} />
      </div>
      <div className="metric-copy">
        <p>{i18n.translateText(card.label)}</p>
        <strong>{card.value}</strong>
        {card.breakdown?.length ? (
          <dl className="metric-breakdown" aria-label={i18n.translateText(`${card.label} breakdown`)}>
            {card.breakdown.map(item => (
              <div key={item.label}>
                <dt>{i18n.translateText(item.label)}</dt>
                <dd>{item.value}</dd>
              </div>
            ))}
          </dl>
        ) : null}
        {showAnnotations ? (
          <>
            <span className={`trend ${trendTone}`}>{i18n.translateText(card.trend)}</span>
            <small>{i18n.translateText(card.detail)}</small>
          </>
        ) : null}
      </div>
    </article>
  );
}
