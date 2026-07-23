import { ArrowRight, Copy, RefreshCw, Search, TimerReset } from 'lucide-react';
import { useMemo, useState } from 'react';

import type {
  ConversationalReadiness,
  DashboardBootPayload,
  DashboardModel,
  HomeSummaryPayload,
} from '../../api/types';
import { Button, StatusBadge } from '../../design';
import type { DashboardViewId } from '../../routes/dashboardSearch';
import { copyText } from '../shared/copyText';
import { OverviewMetrics } from '../overview/OverviewMetrics';
import { buildOverviewMetrics } from '../overview/overviewModel';
import { buildHomeModel } from './homeModel';
import styles from './HomePage.module.css';

export function HomePage({
  model: dashboardModel,
  payload,
  summary,
  readiness,
  refreshing,
  onRefresh,
  onNavigate,
  onOpenCall,
}: {
  model: DashboardModel;
  payload: DashboardBootPayload | null;
  summary?: HomeSummaryPayload;
  readiness?: ConversationalReadiness;
  refreshing: boolean;
  onRefresh: () => void;
  onNavigate: (view: DashboardViewId) => void;
  onOpenCall: (recordId: string) => void;
}) {
  const home = useMemo(
    () => buildHomeModel({ payload, summary, readiness }),
    [payload, readiness, summary],
  );
  const usageMetrics = useMemo(() => buildOverviewMetrics(dashboardModel), [dashboardModel]);
  const [copyStatus, setCopyStatus] = useState('');

  async function copyPrompt(prompt: string, success: string) {
    const copied = await copyText(prompt);
    setCopyStatus(copied ? success : 'Copy unavailable in this browser');
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div>
          <p className={styles.eyebrow}>Usage pulse</p>
          <h1>Overview</h1>
          <p>The important changes first, with direct paths into supporting evidence.</p>
        </div>
        <div className={styles.headerActions}>
          <StatusBadge tone={refreshing ? 'caution' : 'neutral'}>
            {refreshing ? 'Refreshing' : 'Stored snapshot'}
          </StatusBadge>
          <Button variant="primary" onClick={onRefresh} disabled={refreshing}>
            <RefreshCw size={16} /> {refreshing ? 'Refreshing...' : 'Refresh data'}
          </Button>
        </div>
      </header>

      <OverviewMetrics
        metrics={usageMetrics}
        loadedCalls={dashboardModel.calls.length}
        availableCalls={payload?.total_available_rows ?? dashboardModel.calls.length}
      />

      <nav className={styles.actions} aria-label="Home actions">
        <Button
          variant="secondary"
          onClick={() => void copyPrompt(home.starterPrompt, 'Starter prompt copied')}
        >
          <Copy size={16} /> Copy starter prompt
        </Button>
        <Button variant="secondary" onClick={() => onNavigate('explore')}>
          <Search size={16} /> Open Explore
        </Button>
        <Button variant="secondary" onClick={() => onNavigate('limits')}>
          <TimerReset size={16} /> Open Limits
        </Button>
      </nav>

      <p className={styles.copyStatus} role="status" aria-live="polite">{copyStatus}</p>

      <section className={styles.statusGrid} aria-label="Home status">
        {home.statusCards.map(card => (
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
        {home.findings.length ? (
          <div className={styles.findings}>
            {home.findings.map(finding => (
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
        {home.recentEvidence.length ? (
          <ul className={styles.evidenceList}>
            {home.recentEvidence.map(evidence => (
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
