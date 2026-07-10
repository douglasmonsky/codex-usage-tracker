import { ArrowUpRight, ChevronsRight } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { IconButton, StatusBadge } from '../index';
import styles from './Evidence.module.css';
import { compactNumber, type LabCall } from './visualContractData';

type EvidenceTableProps = {
  calls: LabCall[];
  selectedId: string;
  onSelect: (call: LabCall) => void;
};

const toneForSignal = {
  efficient: 'positive',
  watch: 'caution',
  risk: 'risk',
} as const;

export function EvidenceTable({ calls, onSelect, selectedId }: EvidenceTableProps) {
  const tableShellRef = useRef<HTMLDivElement>(null);
  const [canScrollRight, setCanScrollRight] = useState(false);

  useEffect(() => {
    const shell = tableShellRef.current;
    if (!shell) return undefined;
    const update = () => setCanScrollRight(shell.scrollLeft + shell.clientWidth < shell.scrollWidth - 1);
    update();
    shell.addEventListener('scroll', update);
    window.addEventListener('resize', update);
    return () => {
      shell.removeEventListener('scroll', update);
      window.removeEventListener('resize', update);
    };
  }, [calls.length]);

  return (
    <>
      <div ref={tableShellRef} className={styles.tableShell} tabIndex={0} aria-label="Calls table. Scroll horizontally for more columns.">
        <table className={styles.table}>
          <thead>
            <tr>
              <th>Thread</th>
              <th>Time</th>
              <th>Model</th>
              <th>Tokens</th>
              <th>Cache</th>
              <th>Credits</th>
              <th>Signal</th>
              <th aria-label="Open call" />
            </tr>
          </thead>
          <tbody>
            {calls.map((call) => (
              <tr key={call.id} data-selected={call.id === selectedId}>
                <td>
                  <button className={styles.rowButton} type="button" onClick={() => onSelect(call)}>
                    <strong>{call.thread}</strong>
                    <span>{call.id}</span>
                  </button>
                </td>
                <td>{call.time}</td>
                <td>{call.model}</td>
                <td className={styles.numeric}>{compactNumber(call.tokens)}</td>
                <td className={call.cache >= 70 ? styles.cacheGood : styles.cacheRisk}>{call.cache}%</td>
                <td className={styles.numeric}>{call.credits.toFixed(1)}</td>
                <td><StatusBadge tone={toneForSignal[call.signal]}>{call.signal}</StatusBadge></td>
                <td>
                  <IconButton aria-label={`Open ${call.thread}`} onClick={() => onSelect(call)}>
                    <ArrowUpRight />
                  </IconButton>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {canScrollRight ? (
          <div className={styles.scrollFooter}>
            <IconButton
              aria-label="Show more columns"
              className={styles.scrollCue}
              title="Show more columns"
              onClick={() => tableShellRef.current?.scrollBy({ left: 240, behavior: 'smooth' })}
            >
              <ChevronsRight />
            </IconButton>
          </div>
        ) : null}
      </div>
      <div className={styles.mobileList} aria-label="Calls evidence list">
        {calls.map((call) => (
          <button data-selected={call.id === selectedId} key={call.id} type="button" onClick={() => onSelect(call)}>
            <span className={styles.mobileIdentity}><strong>{call.thread}</strong><span>{call.id} / {call.model} / {call.time}</span></span>
            <span className={styles.mobileMetrics}>
              <span><strong>{compactNumber(call.tokens)}</strong><small>tokens</small></span>
              <span><strong>{call.cache}%</strong><small>cache</small></span>
              <StatusBadge tone={toneForSignal[call.signal]}>{call.signal}</StatusBadge>
            </span>
          </button>
        ))}
      </div>
    </>
  );
}
