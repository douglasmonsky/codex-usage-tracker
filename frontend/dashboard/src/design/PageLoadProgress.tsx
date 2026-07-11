import styles from './PageLoadProgress.module.css';

export type PageLoadProgressProps = {
  active: boolean;
  completed?: number;
  total?: number;
  label: string;
  error?: string | null;
  updating?: boolean;
};

export function PageLoadProgress({
  active,
  completed = 0,
  total,
  label,
  error,
  updating = false,
}: PageLoadProgressProps) {
  if (!active && !error) return null;
  if (error) {
    return <div className={styles.error} role="alert">Incomplete page evidence: {error}</div>;
  }

  const determinate = typeof total === 'number' && total > 0;
  const safeCompleted = determinate ? Math.min(Math.max(completed, 0), total) : 0;
  const percent = determinate ? (safeCompleted / total) * 100 : 0;

  return (
    <section className={styles.root} aria-live="polite">
      <div className={styles.copy}>
        <strong>{updating ? 'Updating page evidence' : label}</strong>
        {determinate ? <span>{safeCompleted} of {total} modules ready</span> : <span>Working on full-scope evidence</span>}
      </div>
      <div
        className={styles.track}
        role="progressbar"
        aria-label={label}
        aria-valuemin={determinate ? 0 : undefined}
        aria-valuemax={determinate ? total : undefined}
        aria-valuenow={determinate ? safeCompleted : undefined}
      >
        <span
          className={determinate ? styles.fill : styles.indeterminate}
          style={determinate ? { width: `${percent}%` } : undefined}
        />
      </div>
    </section>
  );
}
