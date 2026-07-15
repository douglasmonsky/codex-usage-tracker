import { forwardRef, useId } from 'react';
import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  ReactNode,
} from 'react';

import { useShellI18n } from '../../app/i18nContext';
import styles from './primitives.module.css';

function classes(...values: Array<string | false | undefined>) {
  return values.filter(Boolean).join(' ');
}

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { children, className, type = 'button', variant = 'secondary', ...props },
  ref,
) {
  const i18n = useShellI18n();
  return (
    <button ref={ref} type={type} className={classes(styles.button, styles[variant], className)} {...props}>
      {localizedNode(children, i18n.translateText)}
    </button>
  );
});

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  'aria-label': string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { 'aria-label': ariaLabel, className, title, type = 'button', ...props },
  ref,
) {
  const i18n = useShellI18n();
  return (
    <button
      ref={ref}
      type={type}
      aria-label={i18n.translateText(ariaLabel)}
      title={typeof title === 'string' ? i18n.translateText(title) : title}
      className={classes(styles.iconButton, className)}
      {...props}
    />
  );
});

type StatusTone = 'neutral' | 'positive' | 'caution' | 'risk' | 'context';

interface StatusBadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: StatusTone;
}

export const StatusBadge = forwardRef<HTMLSpanElement, StatusBadgeProps>(function StatusBadge(
  { children, className, tone = 'neutral', ...props },
  ref,
) {
  const i18n = useShellI18n();
  return (
    <span ref={ref} className={classes(styles.badge, styles[tone], className)} {...props}>
      {localizedNode(children, i18n.translateText)}
    </span>
  );
});

interface SurfaceProps extends HTMLAttributes<HTMLDivElement> {
  tone?: 'panel' | 'subtle';
}

export const Surface = forwardRef<HTMLDivElement, SurfaceProps>(function Surface(
  { className, tone = 'panel', ...props },
  ref,
) {
  return <div ref={ref} className={classes(styles.surface, tone === 'subtle' && styles.surfaceSubtle, className)} {...props} />;
});

interface MetricReadoutProps extends HTMLAttributes<HTMLDivElement> {
  label: ReactNode;
  value: ReactNode;
  detail?: ReactNode;
}

export const MetricReadout = forwardRef<HTMLDivElement, MetricReadoutProps>(function MetricReadout(
  { className, detail, label, value, ...props },
  ref,
) {
  const i18n = useShellI18n();
  return (
    <div ref={ref} className={classes(styles.metric, className)} {...props}>
      <span className={styles.metricLabel}>{localizedNode(label, i18n.translateText)}</span>
      <strong className={styles.metricValue}>{value}</strong>
      {detail ? <span className={styles.metricDetail}>{localizedNode(detail, i18n.translateText)}</span> : null}
    </div>
  );
});

interface SegmentedControlOption<T extends string> {
  label: ReactNode;
  value: T;
  disabled?: boolean;
}

interface SegmentedControlProps<T extends string>
  extends Omit<HTMLAttributes<HTMLDivElement>, 'onChange'> {
  label: string;
  options: ReadonlyArray<SegmentedControlOption<T>>;
  value: T;
  onValueChange: (value: T) => void;
}

export function SegmentedControl<T extends string>({
  className,
  label,
  onValueChange,
  options,
  value,
  ...props
}: SegmentedControlProps<T>) {
  const i18n = useShellI18n();
  return (
    <div role="group" aria-label={i18n.translateText(label)} className={classes(styles.segments, className)} {...props}>
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={option.value === value}
          className={classes(styles.segment, option.value === value && styles.segmentActive)}
          disabled={option.disabled}
          onClick={() => onValueChange(option.value)}
        >
          {localizedNode(option.label, i18n.translateText)}
        </button>
      ))}
    </div>
  );
}

interface ProgressBarProps extends Omit<HTMLAttributes<HTMLDivElement>, 'children'> {
  label: ReactNode;
  value: number;
  max?: number;
  showValue?: boolean;
}

export const ProgressBar = forwardRef<HTMLDivElement, ProgressBarProps>(function ProgressBar(
  { className, label, max = 100, showValue = true, value, ...props },
  ref,
) {
  const i18n = useShellI18n();
  const labelId = useId();
  const safeMax = max > 0 ? max : 100;
  const safeValue = Math.min(Math.max(value, 0), safeMax);
  const percent = Math.round((safeValue / safeMax) * 100);

  return (
    <div ref={ref} className={classes(styles.progress, className)} {...props}>
      <div className={styles.progressHeader}>
        <span id={labelId}>{localizedNode(label, i18n.translateText)}</span>
        {showValue ? <span aria-hidden="true">{percent}%</span> : null}
      </div>
      <div
        role="progressbar"
        aria-labelledby={labelId}
        aria-valuemin={0}
        aria-valuemax={safeMax}
        aria-valuenow={safeValue}
        className={styles.progressTrack}
      >
        <div className={styles.progressFill} style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
});

function localizedNode(node: ReactNode, translate: (value: string) => string): ReactNode {
  return typeof node === 'string' ? translate(node) : node;
}
