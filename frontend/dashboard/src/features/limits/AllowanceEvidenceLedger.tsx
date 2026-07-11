import { Copy, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type KeyboardEvent, type MouseEvent } from 'react';

import { Button, StatusBadge } from '../../design';
import { formatCompact } from '../shared/format';
import type { AllowanceWindowEvidence } from './allowanceModel';
import styles from './AllowanceEvidenceLedger.module.css';

type AllowanceEvidenceLedgerProps = {
  window: AllowanceWindowEvidence;
  onOpenCall: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

const INITIAL_ROW_COUNT = 20;

export function AllowanceEvidenceLedger({
  window,
  onOpenCall,
  onCopyCallLink,
}: AllowanceEvidenceLedgerProps) {
  const [visibleCount, setVisibleCount] = useState(INITIAL_ROW_COUNT);
  const rows = useMemo(() => [...window.points].reverse(), [window.points]);
  const visibleRows = rows.slice(0, visibleCount);

  useEffect(() => setVisibleCount(INITIAL_ROW_COUNT), [window.kind]);

  return (
    <section className={styles.section} aria-labelledby="allowance-evidence-title">
      <div className={styles.header}>
        <div>
          <h2 id="allowance-evidence-title">Supporting windows</h2>
          <p>Exact local evidence behind the selected chart. Linked rows open the underlying call.</p>
        </div>
        <StatusBadge tone={window.kind === 'weekly' ? 'positive' : 'context'}>
          {visibleRows.length} of {rows.length}
        </StatusBadge>
      </div>
      <div className={styles.tableFrame}>
        <table>
          <caption className="sr-only">Allowance evidence windows and linked calls</caption>
          <thead>
            <tr>
              <th scope="col">Observed</th>
              <th scope="col">{window.metric === 'capacity_proxy' ? 'Capacity proxy' : 'Remaining'}</th>
              <th scope="col">Movement</th>
              <th scope="col">Est. credits</th>
              <th scope="col">Evidence</th>
              <th scope="col">Plan</th>
              <th scope="col"><span className="sr-only">Actions</span></th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map(row => (
              <tr
                key={row.id}
                data-linked={Boolean(row.recordId)}
                tabIndex={row.recordId ? 0 : undefined}
                aria-label={row.recordId ? `Open allowance evidence call observed ${row.label}` : undefined}
                onClick={() => row.recordId && onOpenCall(row.recordId)}
                onKeyDown={event => activateRow(event, row.recordId, onOpenCall)}
              >
                <th scope="row">{row.label}</th>
                <td className={styles.numeric}>{window.metric === 'capacity_proxy' ? formatCompact(row.estimate) : `${Math.round(row.estimate)}%`}</td>
                <td className={styles.numeric}>{row.deltaPercent === null ? '—' : `${round(row.deltaPercent)}%`}</td>
                <td className={styles.numeric}>{row.credits === null ? '—' : formatCompact(row.credits)}</td>
                <td><StatusBadge tone={gradeTone(row.grade)}>{gradeLabel(row.grade)}</StatusBadge></td>
                <td>{row.plan}</td>
                <td>
                  {row.recordId ? (
                    <div className={styles.actions}>
                      <button
                        type="button"
                        aria-label={`Open allowance evidence call observed ${row.label}`}
                        title="Open call"
                        onClick={event => handleAction(event, () => onOpenCall(row.recordId as string))}
                      >
                        <Search />
                      </button>
                      <button
                        type="button"
                        aria-label={`Copy link to allowance evidence call observed ${row.label}`}
                        title="Copy call link"
                        onClick={event => handleAction(event, () => onCopyCallLink(row.recordId as string))}
                      >
                        <Copy />
                      </button>
                    </div>
                  ) : <span className={styles.unlinked}>Aggregate</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visibleRows.length ? <p className={styles.empty}>No usable evidence rows are available for this window.</p> : null}
      </div>
      {visibleCount < rows.length ? (
        <Button className={styles.loadMore} onClick={() => setVisibleCount(count => count + INITIAL_ROW_COUNT)}>
          Load more windows
        </Button>
      ) : null}
    </section>
  );
}

function activateRow(
  event: KeyboardEvent<HTMLTableRowElement>,
  recordId: string | null,
  onOpenCall: (recordId: string) => void,
) {
  if (!recordId || (event.key !== 'Enter' && event.key !== ' ')) return;
  event.preventDefault();
  onOpenCall(recordId);
}

function handleAction(event: MouseEvent<HTMLButtonElement>, action: () => void) {
  event.stopPropagation();
  action();
}

function gradeTone(grade: string): 'neutral' | 'positive' | 'caution' | 'risk' | 'context' {
  if (grade.includes('strong')) return 'risk';
  if (grade.includes('possible') || grade.includes('inconclusive')) return 'caution';
  if (grade.includes('no_change') || grade === 'high') return 'positive';
  if (grade.includes('noise')) return 'context';
  return 'neutral';
}

function gradeLabel(grade: string): string {
  return grade.replaceAll('_', ' ');
}

function round(value: number): string {
  return (Math.round(value * 100) / 100).toLocaleString();
}
