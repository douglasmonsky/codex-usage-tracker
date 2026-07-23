import type { ConversationalReadiness } from '../../api/types';
import { useShellI18n } from '../../app/i18nContext';
import styles from './ConversationalAnalysisStatus.module.css';

type Props = { readiness?: ConversationalReadiness | null };

const UNKNOWN: ConversationalReadiness = {
  schema: 'codex-usage-tracker-conversational-readiness-v1',
  state: 'unknown',
  summary: 'Conversational analysis readiness could not be determined from this static payload.',
  next_action: 'Open a live dashboard or run `codex-usage-tracker doctor`.',
  evidence: [],
};

const guidanceKeys: Record<ConversationalReadiness['state'], string> = {
  ready: 'readiness.guidance.ready',
  'restart-required': 'readiness.guidance.restart_required',
  unavailable: 'readiness.guidance.unavailable',
  unknown: 'readiness.guidance.unknown',
};

const stateKeys: Record<ConversationalReadiness['state'], string> = {
  ready: 'readiness.state.ready',
  'restart-required': 'readiness.state.restart_required',
  unavailable: 'readiness.state.unavailable',
  unknown: 'readiness.state.unknown',
};

export function ConversationalAnalysisStatus({ readiness }: Props) {
  const i18n = useShellI18n();
  const status = normalizeConversationalReadiness(readiness);
  const fallbackLabels = [
    ['readiness.fallback.home', 'Home'],
    ['readiness.fallback.explore', 'Explore'],
    ['readiness.fallback.limits', 'Limits'],
    ['readiness.fallback.cli', 'CLI analyze or query'],
  ] as const;
  const action = status.next_action
    ? i18n.translateText(status.next_action)
    : i18n.t(guidanceKeys[status.state], status.summary);
  return (
    <section className={styles.card} aria-labelledby="conversational-analysis-title">
      <div className={styles.heading}>
        <div>
          <p className={styles.eyebrow}>{i18n.t('readiness.eyebrow', 'Conversational analysis')}</p>
          <h2 id="conversational-analysis-title">{i18n.t('readiness.title', 'Analysis readiness')}</h2>
        </div>
        <span className={styles.state}>{i18n.t(stateKeys[status.state], status.state)}</span>
      </div>
      <p>{i18n.translateText(status.summary)}</p>
      <p className={styles.action}>{action}</p>
      <div className={styles.fallbacks}>
        <strong>{i18n.t('readiness.manual_fallback', 'Manual fallback')}</strong>
        <ul>
          {fallbackLabels.map(([key, fallback]) => <li key={key}>{i18n.t(key, fallback)}</li>)}
        </ul>
      </div>
    </section>
  );
}

function normalizeConversationalReadiness(
  readiness?: ConversationalReadiness | null,
): ConversationalReadiness {
  return readiness?.schema === UNKNOWN.schema ? readiness : UNKNOWN;
}
