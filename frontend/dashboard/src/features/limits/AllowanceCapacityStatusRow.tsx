import { StatusBadge } from '../../design';
import type { AllowanceReadout, MetricReadout } from './allowanceIntelligenceModel';
import styles from './LimitsIntelligence.module.css';

type AllowanceCapacityStatusRowProps = {
  readout: Pick<AllowanceReadout, 'weekly' | 'fiveHour' | 'reset' | 'capacity'>;
};

export function AllowanceCapacityStatusRow({ readout }: AllowanceCapacityStatusRowProps) {
  return (
    <section className={styles.capacityStatusRow} role="group" aria-label="Current limit status">
      <StatusCell readout={readout.weekly} />
      <StatusCell readout={readout.fiveHour} />
      <StatusCell readout={readout.reset} />
      <StatusCell readout={readout.capacity} />
    </section>
  );
}

function StatusCell({ readout }: { readout: MetricReadout }) {
  return (
    <div className={styles.capacityStatusCell}>
      <div className={styles.capacityStatusLabel}>
        <span>{readout.label}</span>
        <StatusBadge tone={badgeTone(readout.kind)}>{readout.grade}</StatusBadge>
      </div>
      <strong>{readout.value}</strong>
      <p>{readout.detail}</p>
    </div>
  );
}

function badgeTone(kind: MetricReadout['kind']): 'positive' | 'context' | 'neutral' {
  return kind === 'observed' ? 'positive' : kind === 'estimated' ? 'context' : 'neutral';
}
