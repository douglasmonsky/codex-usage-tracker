import { ChevronLeft, ChevronRight, Copy, ExternalLink } from 'lucide-react';

import type { AllowanceEvidenceRow } from '../../api/types';
import { Button, StatusBadge, Surface } from '../../design';
import { sortAllowanceEvidenceRows } from './allowanceIntelligenceModel';
import styles from './LimitsPage.module.css';

type Props = {
  rows: AllowanceEvidenceRow[];
  page: number;
  hasOlder: boolean;
  loading: boolean;
  onNewer: () => void;
  onOlder: () => void;
  onOpenCall: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
};

export function AllowanceIntelligenceEvidenceTable({
  rows,
  page,
  hasOlder,
  loading,
  onNewer,
  onOlder,
  onOpenCall,
  onCopyCallLink,
}: Props) {
  const ordered = sortAllowanceEvidenceRows(rows);
  return (
    <Surface className={styles.evidencePanel}>
      <div className={styles.panelHeader}>
        <div>
          <p className={styles.eyebrow}>Source evidence</p>
          <h2>Latest supporting intervals</h2>
          <p>Newest first. Each page is bounded to 100 canonical local intervals.</p>
        </div>
        <div className={styles.paginationActions}>
          <Button onClick={onNewer} disabled={page === 1 || loading}><ChevronLeft />Newer</Button>
          <span>Page {page}</span>
          <Button onClick={onOlder} disabled={!hasOlder || loading}>Older<ChevronRight /></Button>
        </div>
      </div>
      <div className={styles.tableScroller}>
        <table className={styles.evidenceTable}>
          <caption className="sr-only">Latest-first allowance intelligence evidence</caption>
          <thead>
            <tr>
              <th scope="col">Observed</th>
              <th scope="col">Used</th>
              <th scope="col">Window</th>
              <th scope="col">Evidence</th>
              <th scope="col">Cohort</th>
              <th scope="col">Provenance</th>
            </tr>
          </thead>
          <tbody>
            {ordered.map((row, index) => {
              const recordId = row.end_record_id ?? row.start_record_id ?? null;
              return (
                <tr key={row.interval_id ?? `${row.end_observed_at}:${index}`}>
                  <th scope="row">{dateTime(row.end_observed_at)}</th>
                  <td className={styles.numeric}>{row.end_used_percent === null ? '—' : `${format(row.end_used_percent)}%`}</td>
                  <td>{row.window_kind === 'weekly' ? 'Weekly' : '5-hour'}</td>
                  <td><StatusBadge tone={tone(row.point_kind)}>{label(row.point_kind, row.censor_reason)}</StatusBadge></td>
                  <td>{row.cohort_key || 'Codex'}</td>
                  <td>
                    {recordId ? (
                      <div className={styles.rowActions}>
                        <button type="button" title="Open source call" onClick={() => onOpenCall(recordId)}><ExternalLink /><span className="sr-only">Open source call</span></button>
                        <button type="button" title="Copy source call link" onClick={() => onCopyCallLink(recordId)}><Copy /><span className="sr-only">Copy source call link</span></button>
                      </div>
                    ) : 'Aggregate'}
                  </td>
                </tr>
              );
            })}
            {!ordered.length ? (
              <tr><td colSpan={6} className={styles.emptyCell}>{loading ? 'Loading evidence…' : 'No evidence in this page.'}</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Surface>
  );
}

function label(kind: AllowanceEvidenceRow['point_kind'], reason: string | null): string {
  if (kind === 'censored') return reason ? `Censored · ${reason.replaceAll('_', ' ')}` : 'Censored';
  return kind === 'positive' ? 'Measured movement' : 'Conflicting signals';
}

function tone(kind: AllowanceEvidenceRow['point_kind']): 'positive' | 'caution' | 'neutral' {
  return kind === 'positive' ? 'positive' : kind === 'conflict' ? 'caution' : 'neutral';
}

function dateTime(value: string): string {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return value;
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }).format(timestamp);
}

function format(value: number): string {
  return new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);
}
