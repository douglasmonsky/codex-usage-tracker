import type { DashboardModuleState } from '../data/dashboardQueryRegistry';
import { useShellI18n } from '../app/i18nContext';
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
  status: DashboardModuleState;
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
  const i18n = useShellI18n();
  if (!active && !error) return null;
  if (!active && error) {
    return (
      <div className={styles.error} role="alert">
        {i18n.translateText(`Incomplete page evidence: ${error}`)}
      </div>
    );
  }

  const determinate = typeof total === 'number' && total > 0;
  const safeCompleted = determinate ? Math.min(Math.max(completed, 0), total) : 0;
  const percent = determinate ? (safeCompleted / total) * 100 : 0;

  return (
    <section className={styles.root} aria-live="polite">
      <div className={styles.copy}>
        <strong>{i18n.translateText(updating ? 'Updating page evidence' : label)}</strong>
        {determinate
          ? <span>{i18n.translateText(`${safeCompleted} of ${total} modules ready`)}</span>
          : <span>{i18n.translateText('Working on full-scope evidence')}</span>}
      </div>
      <div
        className={`${styles.track} ${modules?.length ? styles.segmentedTrack : ''}`}
        role="progressbar"
        aria-label={i18n.translateText(label)}
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
        <div className={styles.modules} aria-label={i18n.translateText(`${i18n.translateText(label)} modules`)}>
          {modules.map(module => (
            <span className={styles.module} key={module.label}>
              {i18n.translateText(module.label)} {i18n.translateText(moduleStatusLabel(module.status))}
            </span>
          ))}
        </div>
      ) : null}
      {error ? <div className={styles.inlineError} role="alert">{i18n.translateText(error)}</div> : null}
    </section>
  );
}

function moduleClassName(status: PageLoadProgressModule['status']): string {
  if (status === 'ready') return styles.segmentReady;
  if (status === 'updating') return styles.segmentUpdating;
  if (status === 'loading') return styles.segmentLoading;
  if (status === 'error') return styles.segmentError;
  return styles.segmentWaiting;
}

function moduleStatusLabel(status: PageLoadProgressModule['status']): string {
  if (status === 'ready') return 'ready';
  if (status === 'updating') return 'updating';
  if (status === 'loading') return 'loading';
  if (status === 'error') return 'unavailable';
  return 'waiting';
}
