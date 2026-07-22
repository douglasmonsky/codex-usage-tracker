import { useEffect, useState } from 'react';

import { loadEvidence, type EvidenceRecord, type EvidenceResult } from '../../api/evidence';
import type { ContextRuntime } from '../../api/types';
import styles from './EvidencePage.module.css';

type ThreadEvidenceProps = {
  evidence: EvidenceResult;
  runtime: ContextRuntime;
  history: 'active' | 'all';
  onOpenCall: (recordId: string) => void;
};

export function ThreadEvidence({ evidence, runtime, history, onOpenCall }: ThreadEvidenceProps) {
  const selectorId = evidence.selector.id;
  const [calls, setCalls] = useState<EvidenceRecord[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    setStatus('loading');
    setCalls([]);
    loadEvidence({ kind: 'thread', selectorId, section: 'calls', limit: 20, history }, runtime)
      .then(page => {
        if (cancelled) return;
        setCalls(page.records);
        setCursor(page.next_cursor);
        setStatus('ready');
      })
      .catch(error => {
        if (cancelled) return;
        setMessage(error instanceof Error ? error.message : 'Thread calls are unavailable.');
        setStatus('error');
      });
    return () => { cancelled = true; };
  }, [history, runtime, selectorId]);

  async function loadMore() {
    if (!cursor || status === 'loading') return;
    setStatus('loading');
    try {
      const page = await loadEvidence(
        { kind: 'thread', selectorId, section: 'calls', limit: 20, history, cursor },
        runtime,
      );
      setCalls(current => [...current, ...page.records]);
      setCursor(page.next_cursor);
      setStatus('ready');
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'More thread calls are unavailable.');
      setStatus('error');
    }
  }

  const summary = evidence.records[0];
  return (
    <section className={styles.content} aria-labelledby="thread-evidence-title">
      <div>
        <p className={styles.eyebrow}>Exact selector · {selectorId}</p>
        <h1 id="thread-evidence-title">Thread evidence</h1>
        <p>{summary?.label ?? selectorId}</p>
      </div>
      {summary ? <MetricGrid metrics={summary.metrics} /> : null}
      <div className={styles.sectionHeader}>
        <div>
          <h2>Calls in this thread</h2>
          <p>Bounded aggregate records, ordered by the evidence service.</p>
        </div>
        {cursor ? (
          <button className="toolbar-button" type="button" onClick={loadMore} disabled={status === 'loading'}>
            Load more calls
          </button>
        ) : null}
      </div>
      {status === 'loading' && calls.length === 0 ? <p role="status">Loading thread calls…</p> : null}
      {status === 'error' ? <p role="alert">{message}</p> : null}
      {calls.length ? (
        <ol className={styles.recordList} aria-label="Thread call evidence">
          {calls.map(record => {
            const recordId = record.selectors.record_id;
            return (
              <li key={record.evidence_id}>
                <div><strong>{record.label}</strong><small>{record.evidence_id}</small></div>
                <MetricLine metrics={record.metrics} />
                {recordId ? <button type="button" onClick={() => onOpenCall(recordId)}>Open call</button> : null}
              </li>
            );
          })}
        </ol>
      ) : status === 'ready' ? <p>No calls were returned for this exact thread.</p> : null}
    </section>
  );
}

function MetricGrid({ metrics }: { metrics: EvidenceRecord['metrics'] }) {
  return (
    <dl className={styles.metricGrid}>
      {Object.entries(metrics).map(([key, value]) => (
        <div key={key}><dt>{label(key)}</dt><dd>{format(value)}</dd></div>
      ))}
    </dl>
  );
}

function MetricLine({ metrics }: { metrics: EvidenceRecord['metrics'] }) {
  return <span className={styles.metricLine}>{Object.entries(metrics).map(([key, value]) => `${label(key)} ${format(value)}`).join(' · ')}</span>;
}

function label(value: string) {
  return value.replaceAll('_', ' ');
}

function format(value: EvidenceRecord['metrics'][string]) {
  return typeof value === 'number' ? value.toLocaleString() : String(value ?? '—');
}
