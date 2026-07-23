import type { AllowanceSeriesRequest } from '../../api/allowanceIntelligence';
import { SegmentedControl } from '../../design';
import styles from './LimitsIntelligence.module.css';

export type RangePreset = NonNullable<AllowanceSeriesRequest['rangePreset']>;
export type Granularity = NonNullable<AllowanceSeriesRequest['granularity']>;

type Props = {
  customEnd: string;
  customReady: boolean;
  customStart: string;
  granularity: Granularity;
  rangePreset: RangePreset;
  onCustomEndChange: (value: string) => void;
  onCustomStartChange: (value: string) => void;
  onGranularityChange: (value: Granularity) => void;
  onRangeChange: (value: RangePreset) => void;
};

export function AllowanceHistoryControls(props: Props) {
  return (
    <>
      <div className={styles.rangeControls}>
        <SegmentedControl
          label="History range"
          options={[{ label: '8w', value: '8w' }, { label: '6m', value: '6m' }]}
          value={props.rangePreset}
          onValueChange={props.onRangeChange}
        />
      </div>
      <details className={styles.advancedControls}>
        <summary>Advanced history controls</summary>
        <div className={styles.advancedControlsBody}>
          <div className={styles.rangeControls}>
            <SegmentedControl
              label="Extended history range"
              options={[{ label: 'All', value: 'all' }, { label: 'Custom', value: 'custom' }]}
              value={props.rangePreset}
              onValueChange={props.onRangeChange}
            />
            <label className={styles.controlField}>Granularity
              <select value={props.granularity} onChange={event => props.onGranularityChange(event.target.value as Granularity)}>
                <option value="cycle">By reset window</option><option value="week">Weekly</option><option value="month">Monthly</option>
              </select>
            </label>
          </div>
          {props.rangePreset === 'custom' ? (
            <div className={styles.customRange}>
              <label>Start date<input type="date" value={props.customStart} onChange={event => props.onCustomStartChange(event.target.value)} /></label>
              <label>End date<input type="date" value={props.customEnd} onChange={event => props.onCustomEndChange(event.target.value)} /></label>
              {!props.customReady ? <span>Choose both dates to load the custom range.</span> : null}
            </div>
          ) : null}
        </div>
      </details>
    </>
  );
}
