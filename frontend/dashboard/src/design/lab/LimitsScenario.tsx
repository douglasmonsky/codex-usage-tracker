import { Download, FlaskConical } from 'lucide-react';
import { useMemo, useState } from 'react';

import { LineChart } from '../../charts/LineChart';
import { Button, MetricReadout, SegmentedControl, StatusBadge, Surface } from '../index';
import { AnswerBand, ScenarioFrame } from './ScenarioFrame';
import styles from './Scenarios.module.css';
import { weeklyAllowanceTrend, type LabScenarioProps } from './visualContractData';

export function LimitsScenario({ onAnnounce }: LabScenarioProps) {
  const [windowType, setWindowType] = useState<'weekly' | 'five-hour'>('weekly');
  const points = useMemo(
    () => weeklyAllowanceTrend.map((point, index) => ({
      ...point,
      value: windowType === 'weekly' ? point.value : Math.max(28, point.value - 20 + (index % 3) * 11),
      low: windowType === 'weekly' ? point.value - 6 : Math.max(12, point.value - 34),
      high: windowType === 'weekly' ? point.value + 7 : Math.min(100, point.value + 10),
    })),
    [windowType],
  );

  return (
    <ScenarioFrame
      eyebrow="Allowance intelligence"
      title="Limits"
      description="Observed allowance behavior, evidence grading, and uncertainty without pretending to read an internal ledger."
      actions={
        <>
          <Button onClick={() => onAnnounce('Allowance hypothesis queued')}><FlaskConical />Test change</Button>
          <Button variant="primary" onClick={() => onAnnounce('Strict allowance evidence exported')}><Download />Export evidence</Button>
        </>
      }
    >
      <AnswerBand
        label="Candidate regime change"
        title="Weekly movement shifted after June 22, but outside usage remains plausible"
        detail="Three observed windows fall below the prior local range. The evidence is useful but not yet strong enough for a broad allowance claim."
        confidence="Possible change"
        evidence="3 windows / medium evidence"
        tone="caution"
      />

      <div className={styles.metricGrid}>
        <Surface><MetricReadout label="Observed windows" value="11" detail="8 complete / 3 partial" /></Surface>
        <Surface><MetricReadout label="Explained movement" value="76%" detail="Token-derived estimate range" /></Surface>
        <Surface><MetricReadout label="Candidate change" value="Jun 22" detail="Posterior confidence: medium" /></Surface>
        <Surface><MetricReadout label="Outside usage gap" value="14%" detail="Other surface activity possible" /></Surface>
      </div>

      <Surface className={styles.chartPanel}>
        <div className={styles.panelHeader}>
          <div><h2>{windowType === 'weekly' ? 'Weekly allowance evidence' : '5-hour rolling context'}</h2><p>Confidence ranges, resets, and missing observations belong on the plot.</p></div>
          <SegmentedControl
            label="Allowance window"
            options={[{ label: 'Weekly', value: 'weekly' }, { label: '5-hour', value: 'five-hour' }]}
            value={windowType}
            onValueChange={setWindowType}
          />
        </div>
        <LineChart
          height={310}
          yLabel="Percent remaining"
          valueFormatter={(value) => `${Math.round(value)}%`}
          series={[{
            id: windowType,
            label: windowType === 'weekly' ? 'Observed weekly remaining' : 'Noisy 5-hour remaining',
            color: windowType === 'weekly' ? 'var(--signal-selection)' : 'var(--signal-caution)',
            points,
          }]}
        />
      </Surface>

      <div className={styles.analysisGrid}>
        <Surface>
          <div className={styles.panelHeader}><div><h2>Evidence grade</h2><p>What supports and weakens this result.</p></div><StatusBadge tone="caution">Possible regime change</StatusBadge></div>
          <p>Observed movement is directionally consistent across three weekly windows, but the number of complete windows is still small.</p>
        </Surface>
        <Surface tone="subtle">
          <div className={styles.panelHeader}><div><h2>Caveats</h2><p>Required before sharing.</p></div></div>
          <p>Manual snapshots, missing observations, resets, and usage outside the local Codex logs can all reduce attribution confidence.</p>
        </Surface>
      </div>
    </ScenarioFrame>
  );
}
