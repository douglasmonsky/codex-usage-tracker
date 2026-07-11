import { ArrowRight, Gauge, ListTree } from 'lucide-react';

import { Button, StatusBadge, Surface } from '../../design';
import type { OverviewFindingView } from './overviewModel';
import type { OverviewNavigationTarget } from './overviewNavigation';
import styles from './OverviewPage.module.css';

type OverviewFindingRailProps = {
  findings: OverviewFindingView[];
  onOpenFinding: (finding: OverviewFindingView) => void;
  onNavigateView: (view: OverviewNavigationTarget) => void;
};

export function OverviewFindingRail({ findings, onOpenFinding, onNavigateView }: OverviewFindingRailProps) {
  return (
    <Surface className={styles.findingsPanel}>
      <div className={styles.panelHeader}>
        <div><h2>Needs attention</h2><p>Endpoint-ranked patterns with evidence scope and a next action.</p></div>
        <StatusBadge tone={findings.length ? 'risk' : 'positive'}>{findings.length} findings</StatusBadge>
      </div>
      {findings.length ? (
        <div className={styles.findingList}>
          {findings.slice(0, 4).map(finding => (
            <button className={styles.findingButton} key={finding.id} type="button" onClick={() => onOpenFinding(finding)}>
              <i className={styles.findingSignal} data-severity={finding.severity} />
              <span className={styles.findingCopy}>
                <strong>{finding.title}</strong>
                <span>{finding.why}</span>
                <small>{finding.evidenceGrade} evidence / {finding.scope} / {freshnessLabel(finding.freshness)}</small>
              </span>
              <span className={styles.findingCount}>{supportCountLabel(finding.supportCount)}</span>
              <ArrowRight aria-hidden="true" size={15} />
            </button>
          ))}
        </div>
      ) : <p className={styles.empty}>No ranked recommendation is present in the current scope.</p>}
      <div className={styles.railActions}>
        <Button onClick={() => onNavigateView('investigator')}><ListTree /> Open Investigator</Button>
        <Button onClick={() => onNavigateView('usage-drain')}><Gauge /> Review limits</Button>
        <Button variant="ghost" onClick={() => onNavigateView('threads')}>Review threads <ArrowRight /></Button>
      </div>
    </Surface>
  );
}

function freshnessLabel(value: string): string {
  if (!value) return 'snapshot evidence';
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

function supportCountLabel(count: number): string {
  return `${count} ${count === 1 ? 'call' : 'calls'}`;
}
