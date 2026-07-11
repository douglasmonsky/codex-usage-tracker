import { ArrowRight, Download } from 'lucide-react';

import { LineChart } from '../../charts/LineChart';
import { Button, IconButton, MetricReadout, StatusBadge, Surface } from '../index';
import { EvidenceTable } from './EvidenceTable';
import { AnswerBand, ScenarioFrame } from './ScenarioFrame';
import styles from './Scenarios.module.css';
import {
  compactNumber,
  findings,
  labCalls,
  tokenFlow,
  usageTrend,
  type LabCall,
  type LabScenarioProps,
} from './visualContractData';

type OverviewScenarioProps = LabScenarioProps & {
  onSelectCall: (call: LabCall) => void;
};

export function OverviewScenario({ onAnnounce, onNavigate, onSelectCall }: OverviewScenarioProps) {
  const totalTokens = labCalls.reduce((sum, call) => sum + call.tokens, 0);
  const averageCache = Math.round(labCalls.reduce((sum, call) => sum + call.cache, 0) / labCalls.length);
  const totalCredits = labCalls.reduce((sum, call) => sum + call.credits, 0);

  return (
    <ScenarioFrame
      eyebrow="Usage pulse"
      title="Overview"
      description="The important changes first, with direct paths into supporting evidence."
      actions={
        <>
          <IconButton aria-label="Export overview" onClick={() => onAnnounce('Overview export prepared')}><Download /></IconButton>
          <Button variant="primary" onClick={() => onNavigate('investigate')}>Review findings <ArrowRight /></Button>
        </>
      }
    >
      <AnswerBand
        label="Highest-priority change"
        title="Two threads account for most avoidable context reloads"
        detail="Repeated file discovery and shell inspection loops explain 31% of high-token calls in the loaded scope."
        confidence="High confidence"
        evidence="38 linked calls / active history"
      />

      <div className={styles.metricGrid}>
        <Surface><MetricReadout label="Calls loaded" value="5,000" detail="42,318 indexed" /></Surface>
        <Surface>
          <MetricReadout
            label="Total tokens"
            value={compactNumber(totalTokens)}
            detail={tokenFlow.map((item) => `${item.label} ${item.value}k`).join(' / ')}
          />
        </Surface>
        <Surface><MetricReadout label="Cache reuse" value={`${averageCache}%`} detail="Up 6 points in recent calls" /></Surface>
        <Surface><MetricReadout label="Estimated credits" value={totalCredits.toFixed(1)} detail="Estimate confidence: medium" /></Surface>
      </div>

      <div className={styles.analysisGrid}>
        <Surface className={styles.chartPanel}>
          <div className={styles.panelHeader}>
            <div><h2>Recent usage movement</h2><p>Recent dates are shown first; scroll left for earlier history.</p></div>
            <div className={styles.chartSummary}><strong>58%</strong><span>+11 points</span></div>
          </div>
          <LineChart
            height={244}
            yLabel="Relative usage"
            valueFormatter={(value) => `${Math.round(value)}%`}
            series={[{ id: 'usage', label: 'Observed movement', color: 'var(--signal-selection)', points: usageTrend }]}
          />
        </Surface>

        <Surface>
          <div className={styles.panelHeader}>
            <div><h2>Needs attention</h2><p>Ranked by evidence strength and likely impact.</p></div>
            <StatusBadge tone="risk">3 findings</StatusBadge>
          </div>
          <div className={styles.findingList}>
            {findings.map((finding) => (
              <button
                className={styles.findingButton}
                data-selected={finding.id === 'rediscovery'}
                key={finding.id}
                type="button"
                onClick={() => onNavigate('investigate')}
              >
                <i className={styles.findingSignal} data-tone={finding.severity} />
                <span className={styles.findingCopy}><strong>{finding.title}</strong><span>{finding.confidence}</span></span>
                <span className={styles.findingEvidence}>{finding.evidence}</span>
              </button>
            ))}
          </div>
        </Surface>
      </div>

      <div>
        <div className={styles.panelHeader}>
          <div><h2>Recent calls</h2><p>Loaded scope only. Open any row without leaving the evidence trail.</p></div>
          <Button onClick={() => onNavigate('explore')}>Explore all calls</Button>
        </div>
        <EvidenceTable calls={labCalls.slice(0, 4)} selectedId={labCalls[0].id} onSelect={onSelectCall} />
      </div>
    </ScenarioFrame>
  );
}
