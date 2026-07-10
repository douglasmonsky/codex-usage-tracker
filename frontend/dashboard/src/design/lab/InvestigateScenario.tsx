import { FlaskConical, Share2 } from 'lucide-react';
import { useState } from 'react';

import { Button, StatusBadge, Surface } from '../index';
import { AnswerBand, ScenarioFrame } from './ScenarioFrame';
import evidenceStyles from './Evidence.module.css';
import styles from './Scenarios.module.css';
import { compactNumber, evidenceRows, findings, type LabScenarioProps } from './visualContractData';

export function InvestigateScenario({ onAnnounce, onNavigate }: LabScenarioProps) {
  const [selectedId, setSelectedId] = useState(findings[0].id);
  const selected = findings.find((finding) => finding.id === selectedId) ?? findings[0];

  return (
    <ScenarioFrame
      eyebrow="Root-cause workspace"
      title="Investigate"
      description="One ranked finding, one evidence ledger, and one explicit verification path."
      actions={
        <>
          <Button onClick={() => onAnnounce('Hypothesis run queued')}><FlaskConical />Test hypothesis</Button>
          <Button variant="primary" onClick={() => onAnnounce('Strict local evidence bundle prepared')}><Share2 />Export evidence</Button>
        </>
      }
    >
      <AnswerBand
        label="Selected finding"
        title={selected.title}
        detail={selected.detail}
        confidence={selected.confidence}
        evidence={selected.evidence}
        tone={selected.severity === 'risk' ? 'risk' : selected.severity === 'watch' ? 'caution' : 'positive'}
      />

      <div className={styles.analysisGrid}>
        <Surface>
          <div className={styles.panelHeader}>
            <div><h2>Ranked findings</h2><p>Scope, confidence, and evidence remain visible while comparing.</p></div>
            <StatusBadge tone="context">Stored diagnostics</StatusBadge>
          </div>
          <div className={styles.findingList}>
            {findings.map((finding) => (
              <button
                className={styles.findingButton}
                data-selected={finding.id === selectedId}
                key={finding.id}
                type="button"
                onClick={() => setSelectedId(finding.id)}
              >
                <i className={styles.findingSignal} data-tone={finding.severity} />
                <span className={styles.findingCopy}><strong>{finding.title}</strong><span>{finding.detail}</span></span>
                <span className={styles.findingEvidence}>{finding.evidence}</span>
              </button>
            ))}
          </div>
        </Surface>

        <Surface tone="subtle">
          <div className={styles.panelHeader}><div><h2>Recommended change</h2><p>Generated from aggregate and local-index evidence.</p></div></div>
          <p>Keep a short repository orientation note and reuse one scoped inspection command before reopening the same file set.</p>
          <Button variant="primary" onClick={() => onNavigate('explore')}>Verify in Calls</Button>
        </Surface>
      </div>

      <section>
        <div className={styles.panelHeader}>
          <div><h2>Evidence ledger</h2><p>Every row links the conclusion back to inspectable activity.</p></div>
          <StatusBadge tone="neutral">4 groups</StatusBadge>
        </div>
        <div className={evidenceStyles.tableShell} tabIndex={0} aria-label="Investigation evidence ledger">
          <table className={evidenceStyles.table}>
            <thead><tr><th>Thread</th><th>Pattern</th><th>Events</th><th>Tokens</th><th>Confidence</th><th>Action</th></tr></thead>
            <tbody>
              {evidenceRows.map((row) => (
                <tr key={`${row.thread}-${row.pattern}`}>
                  <td><strong>{row.thread}</strong></td>
                  <td>{row.pattern}</td>
                  <td>{row.events}</td>
                  <td>{compactNumber(row.tokens)}</td>
                  <td><StatusBadge tone={row.confidence === 'High' ? 'positive' : 'caution'}>{row.confidence}</StatusBadge></td>
                  <td><Button variant="ghost" onClick={() => onNavigate('explore')}>Open calls</Button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <p className={styles.methodNote}>Method: repeated safe file identities, normalized command roots, and call-level token evidence. Indexed snippets stay local and are not included in this shareable summary.</p>
    </ScenarioFrame>
  );
}
