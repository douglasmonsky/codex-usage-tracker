import type { EvidenceRecord, EvidenceResult } from '../../api/evidence';
import styles from './EvidencePage.module.css';

export function FindingEvidence({ evidence, history }: { evidence: EvidenceResult; history: 'active' | 'all' }) {
  const subject = evidence.subject ?? {};
  const title = text(subject.title) ?? 'Finding evidence';
  const limitations = list(subject.caveat_codes);
  return (
    <section className={styles.content} aria-labelledby="finding-evidence-title">
      <div>
        <p className={styles.eyebrow}>Persisted finding · {evidence.selector.id}</p>
        <h1 id="finding-evidence-title">{title}</h1>
        {text(subject.statement) ? <p className={styles.claim}>{text(subject.statement)}</p> : null}
      </div>
      <dl className={styles.factGrid}>
        <Fact label="Claim type" value={text(subject.claim_type)} />
        <Fact label="Confidence" value={text(subject.confidence)} />
        <Fact label="Severity" value={text(subject.severity)} />
        <Fact label="Analysis" value={text(subject.analysis_id)} />
        <Fact label="History scope" value={history} />
      </dl>
      <div>
        <h2>Limitations</h2>
        {limitations.length ? (
          <ul className={styles.chipList}>{limitations.map(value => <li key={value}>{value}</li>)}</ul>
        ) : <p>No persisted limitation codes were supplied.</p>}
      </div>
      <LinkedEvidence records={evidence.records} />
    </section>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  return <div><dt>{label}</dt><dd>{value ?? 'Not supplied'}</dd></div>;
}

function LinkedEvidence({ records }: { records: EvidenceRecord[] }) {
  return (
    <div>
      <h2>Linked evidence</h2>
      <ol className={styles.recordList} aria-label="Finding linked evidence">
        {records.map(record => (
          <li key={record.evidence_id}>
            <div><strong>{record.label}</strong><small>{record.source_schema}</small></div>
            <span className={styles.metricLine}>{Object.entries(record.metrics).map(([key, value]) => (
              `${key.replaceAll('_', ' ')} ${typeof value === 'number' ? value.toLocaleString() : String(value ?? '—')}`
            )).join(' · ')}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null;
}

function list(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}
