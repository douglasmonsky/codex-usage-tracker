import styles from './PageLoadProgress.module.css';

export type PageLoadProgressProps = {
  active: boolean;
  completed?: number;
  total?: number;
  label: string;
  error?: string | null;
  modules?: PageLoadProgressModule[];
  updating?: boolean;
};

export type PageLoadProgressModule = {
  label: string;
  status: 'error' | 'loading' | 'ready' | 'waiting';
};

export function PageLoadProgress({
  active,
  completed = 0,
  total,
  label,
  error,
  modules,
  updating = false,
}: PageLoadProgressProps) {
  if (!active && !error) return null;
  if (!active && error) {
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
        className={`${styles.track} ${modules?.length ? styles.segmentedTrack : ''}`}
        role="progressbar"
        aria-label={label}
        aria-valuemin={determinate ? 0 : undefined}
        aria-valuemax={determinate ? total : undefined}
        aria-valuenow={determinate ? safeCompleted : undefined}
      >
        {modules?.length
          ? modules.map(module => (
              <span
                className={`${styles.segment} ${moduleClassName(module.status)}`}
                key={module.label}
              />
            ))
          : <span
              className={determinate ? styles.fill : styles.indeterminate}
              style={determinate ? { width: `${percent}%` } : undefined}
            />}
      </div>
      {modules?.length ? (
        <div className={styles.modules} aria-label={`${label} modules`}>
          {modules.map(module => (
            <span className={styles.module} key={module.label}>
              {module.label} {moduleStatusLabel(module.status)}
            </span>
          ))}
        </div>
      ) : null}
      {error ? <div className={styles.inlineError} role="alert">{error}</div> : null}
    </section>
  );
}

function moduleClassName(status: PageLoadProgressModule['status']): string {
  if (status === 'ready') return styles.segmentReady;
  if (status === 'loading') return styles.segmentLoading;
  if (status === 'error') return styles.segmentError;
  return styles.segmentWaiting;
}

function moduleStatusLabel(status: PageLoadProgressModule['status']): string {
  if (status === 'ready') return 'ready';
  if (status === 'loading') return 'loading';
  if (status === 'error') return 'unavailable';
  return 'waiting';
}
