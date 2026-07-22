import type { EvidenceEnvelope, EvidenceRecord } from '../../api/evidence';
import styles from './EvidencePage.module.css';

export function FindingEvidence({ envelope }: { envelope: EvidenceEnvelope }) {
  const subject = envelope.result.subject ?? {};
  const title = text(subject.title) ?? 'Finding evidence';
  const limitations = list(subject.caveat_codes);
  return (
    <section className={styles.content} aria-labelledby="finding-evidence-title">
      <div>
        <p className={styles.eyebrow}>Persisted finding · {envelope.result.selector.id}</p>
        <h1 id="finding-evidence-title">{title}</h1>
        {text(subject.statement) ? <p className={styles.claim}>{text(subject.statement)}</p> : null}
      </div>
      <dl className={styles.factGrid}>
        <Fact label="Claim type" value={text(subject.claim_type)} />
        <Fact label="Confidence" value={text(subject.confidence)} />
        <Fact label="Severity" value={text(subject.severity)} />
        <Fact label="Analysis" value={text(subject.analysis_id)} />
        <Fact label="History scope" value={envelope.scope.history} />
        <Fact label="Privacy scope" value={envelope.scope.privacy_mode} />
        <Fact label="Filters" value={scopeFilters(envelope.scope.filters)} />
      </dl>
      <div>
        <h2>Limitations</h2>
        {limitations.length ? (
          <ul className={styles.chipList}>{limitations.map(value => <li key={value}>{value}</li>)}</ul>
        ) : <p>No persisted limitation codes were supplied.</p>}
      </div>
      <LinkedEvidence records={envelope.result.records} />
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

function scopeFilters(filters: Record<string, unknown>): string {
  const values = Object.entries(filters).map(([key, value]) => `${key}: ${String(value)}`);
  return values.length ? values.join(', ') : 'None';
}
