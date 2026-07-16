import type { AllowanceSeriesPayload } from '../../api/allowanceIntelligenceTypes';
import styles from './AllowanceCapacityLegend.module.css';
import {
  allowancePlanColor,
  allowancePlanLabel,
  normalizeAllowancePlanType,
} from './allowancePlanPresentation';

type AllowanceCapacityLegendProps = {
  series: AllowanceSeriesPayload;
};

export function AllowanceCapacityLegend({ series }: AllowanceCapacityLegendProps) {
  const planTypes = [...new Set(
    series.capacity_history.points.map(point => normalizeAllowancePlanType(point.plan_type)),
  )];

  return (
    <div
      className={styles.capacityLegend}
      role="group"
      aria-label="Capacity chart legend"
      data-localization-attributes="aria-label"
    >
      <ul
        className={styles.legendKey}
        aria-label="Subscription plan key"
        data-localization-attributes="aria-label"
      >
        <li className={styles.legendKeyLabel}>Plan</li>
        {planTypes.map(planType => (
          <li key={planType}>
            <span
              className={styles.planSwatch}
              style={{ backgroundColor: allowancePlanColor(planType) }}
              aria-hidden="true"
            />
            {allowancePlanLabel(planType)}
          </li>
        ))}
      </ul>
      <ul
        className={styles.legendKey}
        aria-label="Chart mark key"
        data-localization-attributes="aria-label"
      >
        <li className={styles.legendKeyLabel}>Mark</li>
        <li><span className={styles.observedMark} aria-hidden="true" />Observed reset window</li>
        <li><span className={styles.medianMark} aria-hidden="true" />Trailing 8-window median</li>
      </ul>
    </div>
  );
}
