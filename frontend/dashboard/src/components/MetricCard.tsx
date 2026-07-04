import { Activity, CircleDollarSign, Database, Gauge, PhoneCall, type LucideIcon } from 'lucide-react';

import type { MetricCard as MetricCardModel } from '../api/types';

const iconByLabel: Record<string, LucideIcon> = {
  'Cache Hit Rate': Database,
  'Estimated Cost': CircleDollarSign,
  'Total Calls': PhoneCall,
  'Total Tokens': Activity,
  'Usage Remaining': Gauge,
};

export function MetricCard({ card }: { card: MetricCardModel }) {
  const Icon = iconByLabel[card.label] ?? Activity;
  const trendTone = card.trend.startsWith('down') || card.trend.includes('risk') ? 'negative' : 'positive';

  return (
    <article className={`metric-card metric-card-${card.tone}`}>
      <div className="metric-icon" aria-hidden="true">
        <Icon size={22} />
      </div>
      <div className="metric-copy">
        <p>{card.label}</p>
        <strong>{card.value}</strong>
        <span className={`trend ${trendTone}`}>{card.trend}</span>
        <small>{card.detail}</small>
      </div>
    </article>
  );
}
