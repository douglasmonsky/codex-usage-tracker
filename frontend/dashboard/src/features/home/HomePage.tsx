import { ArrowRight, Copy, RefreshCw, Search, TimerReset } from 'lucide-react';
import { useMemo, useState } from 'react';

import type {
  ConversationalReadiness,
  DashboardBootPayload,
  HomeSummaryPayload,
} from '../../api/types';
import { Button, StatusBadge } from '../../design';
import type { DashboardViewId } from '../../routes/dashboardSearch';
import { copyText } from '../shared/copyText';
import { buildHomeModel } from './homeModel';
import styles from './HomePage.module.css';

export function HomePage({
  payload,
  summary,
  readiness,
  refreshing,
  onRefresh,
  onNavigate,
  onOpenCall,
}: {
  payload: DashboardBootPayload | null;
  summary?: HomeSummaryPayload;
  readiness?: ConversationalReadiness;
  refreshing: boolean;
  onRefresh: () => void;
  onNavigate: (view: DashboardViewId) => void;
  onOpenCall: (recordId: string) => void;
}) {
  const model = useMemo(
    () => buildHomeModel({ payload, summary, readiness }),
    [payload, readiness, summary],
  );
  const [copyStatus, setCopyStatus] = useState('');

  async function copyPrompt(prompt: string, success: string) {
    const copied = await copyText(prompt);
    setCopyStatus(copied ? success : 'Copy unavailable in this browser');
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Evidence Console</p>
          <h1>Home</h1>
          <p>Check readiness, start an investigation, and open the strongest recent evidence.</p>
        </div>
        <div className={styles.actions}>
          <Button
            variant="secondary"
            onClick={() => void copyPrompt(model.starterPrompt, 'Starter prompt copied')}
          >
            <Copy size={16} /> Copy starter prompt
          </Button>
          <Button variant="secondary" onClick={() => onNavigate('explore')}>
            <Search size={16} /> Open Explore
          </Button>
          <Button variant="secondary" onClick={() => onNavigate('limits')}>
            <TimerReset size={16} /> Open Limits
          </Button>
          <Button variant="primary" onClick={onRefresh} disabled={refreshing}>
            <RefreshCw size={16} /> {refreshing ? 'Refreshing...' : 'Refresh Home'}
          </Button>
        </div>
      </header>

      <p className={styles.copyStatus} role="status" aria-live="polite">{copyStatus}</p>

      <section className={styles.statusGrid} aria-label="Home status">
        {model.statusCards.map(card => (
          <article className={styles.statusCard} key={card.id}>
            <div className={styles.cardHeading}>
              <span>{card.label}</span>
              <StatusBadge tone={card.tone}>{card.value}</StatusBadge>
            </div>
            <strong>{card.value}</strong>
            <p>{card.detail}</p>
          </article>
        ))}
      </section>

      <section className={styles.section} aria-label="Recent findings">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Bounded persisted evidence</p>
            <h2>Recent findings</h2>
          </div>
          <span>Up to 3 high-confidence findings</span>
        </div>
        {model.findings.length ? (
          <div className={styles.findings}>
            {model.findings.map(finding => (
              <article className={styles.finding} key={finding.finding_id}>
                <div className={styles.cardHeading}>
                  <h3>{finding.title}</h3>
                  <StatusBadge tone="positive">High confidence</StatusBadge>
                </div>
                <p>{finding.summary}</p>
                <strong>{finding.action}</strong>
                <div className={styles.inlineActions}>
                  <Button variant="secondary" onClick={() => onOpenCall(finding.evidence.record_id)}>
                    Open evidence <ArrowRight size={15} />
                  </Button>
                  <Button
                    variant="secondary"
                    onClick={() => void copyPrompt(finding.follow_up_prompt, 'Follow-up copied')}
                  >
                    <Copy size={15} /> Copy follow-up
                  </Button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className={styles.empty}>No high-confidence findings are persisted for the current index.</p>
        )}
      </section>

      <section className={styles.section} aria-label="Recent evidence">
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Active index</p>
            <h2>Recent evidence</h2>
          </div>
          <span>Up to 5 aggregate records</span>
        </div>
        {model.recentEvidence.length ? (
          <ul className={styles.evidenceList}>
            {model.recentEvidence.map(evidence => (
              <li key={evidence.evidence_id}>
                <div>
                  <strong>{evidence.label}</strong>
                  <span>{evidence.detail}</span>
                </div>
                <Button variant="secondary" onClick={() => onOpenCall(evidence.record_id)}>
                  Open recent evidence <ArrowRight size={15} />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className={styles.empty}>No recent aggregate evidence is available.</p>
        )}
      </section>
    </div>
  );
}
