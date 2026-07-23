import type { EvidenceMetricValue, EvidenceResult } from '../../api/evidence';
import styles from './EvidencePage.module.css';

export function AllowanceEvidence({
  evidence,
  analysisId,
  history,
}: {
  evidence: EvidenceResult;
  analysisId: string;
  history: 'active' | 'all';
}) {
  const record = evidence.records[0];
  return (
    <section className={styles.content} aria-labelledby="allowance-evidence-title">
      <div>
        <p className={styles.eyebrow}>Persisted transition · {evidence.selector.id}</p>
        <h1 id="allowance-evidence-title">Allowance evidence</h1>
        <p>{record?.label ?? 'The selected allowance transition is unavailable.'}</p>
      </div>
      <dl className={styles.factGrid}>
        <div><dt>Analysis</dt><dd>{analysisId}</dd></div>
        <div><dt>History scope</dt><dd>{history}</dd></div>
        <div><dt>Source schema</dt><dd>{record?.source_schema ?? 'Not supplied'}</dd></div>
      </dl>
      {record ? (
        <div>
          <h2>Supporting transition facts</h2>
          <dl className={styles.metricGrid}>
            {Object.entries(record.metrics).map(([key, value]) => (
              <div key={key}><dt>{key.replaceAll('_', ' ')}</dt><dd>{format(value)}</dd></div>
            ))}
          </dl>
        </div>
      ) : null}
    </section>
  );
}

function format(value: EvidenceMetricValue) {
  if (typeof value === 'number') return value.toLocaleString();
  return String(value ?? '—');
}
