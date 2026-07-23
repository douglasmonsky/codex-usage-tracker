import { StatusBadge, Surface } from '../../design';
import type {
  AllowanceAnalysisPayload,
  AllowanceCapacityBoundary,
  AllowanceEvidenceRow,
} from '../../api/allowanceIntelligenceTypes';
import styles from './AllowanceCapacity.module.css';

type AllowanceCapacityChangeTimelineProps = {
  analysis: AllowanceAnalysisPayload | undefined;
  evidenceRows: AllowanceEvidenceRow[];
  running: boolean;
};

export function AllowanceCapacityChangeTimeline({
  analysis,
  evidenceRows,
  running,
}: AllowanceCapacityChangeTimelineProps) {
  const boundaries = [...(analysis?.boundaries ?? [])]
    .sort((left, right) => Date.parse(right.effective_at) - Date.parse(left.effective_at));
  const hasSupportedChanges = boundaries.length > 0;

  return (
    <Surface className={styles.capacityChangePanel}>
      <div className={styles.capacityChangeHeader}>
        <div>
          <p className={styles.capacityChangeEyebrow}>Capacity changes</p>
          <h2>{timelineTitle(analysis, running, hasSupportedChanges)}</h2>
        </div>
        <StatusBadge tone={hasSupportedChanges ? 'caution' : analysis?.status === 'no_supported_change' ? 'positive' : 'neutral'}>
          {running ? 'Analyzing' : hasSupportedChanges ? `${boundaries.length} supported` : statusLabel(analysis)}
        </StatusBadge>
      </div>

      {hasSupportedChanges ? (
        <ol
          className={styles.capacityChangeList}
          aria-label="Supported capacity changes"
          data-localization-attributes="aria-label"
        >
          {boundaries.map(boundary => (
            <BoundaryItem
              key={boundary.boundary_id}
              analysisId={analysis?.snapshot_id ?? null}
              boundary={boundary}
              evidenceId={boundaryEvidenceId(boundary, evidenceRows)}
            />
          ))}
        </ol>
      ) : (
        <p className={styles.capacityChangeExplanation}>{timelineExplanation(analysis, running)}</p>
      )}

      <dl className={styles.capacityChangeMeta}>
        <div><dt>Eligible reset windows</dt><dd>{analysis?.eligible_cycle_count ?? '—'}</dd></div>
        <div><dt>Last analyzed</dt><dd>{analysis?.generated_at ? formatDateTime(analysis.generated_at) : running ? 'In progress' : 'Not yet'}</dd></div>
      </dl>
    </Surface>
  );
}

function BoundaryItem({
  analysisId,
  boundary,
  evidenceId,
}: {
  analysisId: string | null;
  boundary: AllowanceCapacityBoundary;
  evidenceId: string | null;
}) {
  const before = boundary.effect_size.median_before_credits_per_percent;
  const after = boundary.effect_size.median_after_credits_per_percent;
  const deltaPercent = before === 0 ? null : ((after - before) / before) * 100;
  const direction = after < before ? 'decreased' : after > before ? 'increased' : 'changed';
  const accessibleLabel = `Credits per 1% ${direction} ${formatCredits(before)} to ${formatCredits(after)} on ${formatDate(boundary.effective_at)}`;
  return (
    <li className={styles.capacityChangeItem} aria-label={accessibleLabel}>
      <time dateTime={boundary.effective_at}>{formatDate(boundary.effective_at)}</time>
      <div className={styles.capacityChangeDetail}>
        <div>
          <span className={styles.capacityChangeType}>Supported change</span>
          <strong>Credits per 1% {direction}</strong>
          <p>{formatCredits(before)} → {formatCredits(after)}{deltaPercent === null ? '' : ` (${formatSignedPercent(deltaPercent)})`}</p>
        </div>
        {analysisId && evidenceId ? (
          <a
            className={styles.capacityEvidenceLink}
            href={allowanceEvidenceHref(analysisId, evidenceId)}
            aria-label={`Open supporting Evidence for ${boundary.boundary_id}`}
          >
            View Evidence
          </a>
        ) : null}
      </div>
    </li>
  );
}

function boundaryEvidenceId(
  boundary: AllowanceCapacityBoundary,
  rows: AllowanceEvidenceRow[],
): string | null {
  const match = rows.find(row => (
    row.cycle_id === boundary.after_cycle_id || row.cycle_id === boundary.before_cycle_id
  ) && row.interval_id);
  return match?.interval_id ?? null;
}

function allowanceEvidenceHref(analysisId: string, evidenceId: string): string {
  const params = new URLSearchParams({
    view: 'evidence',
    kind: 'allowance',
    analysis: analysisId,
    evidence: evidenceId,
  });
  if (new URLSearchParams(window.location.search).get('history') === 'all') params.set('history', 'all');
  return `?${params.toString()}`;
}

function timelineTitle(
  analysis: AllowanceAnalysisPayload | undefined,
  running: boolean,
  hasSupportedChanges: boolean,
): string {
  if (running) return 'Checking capacity history';
  if (hasSupportedChanges) return analysis?.boundaries?.length === 1
    ? '1 reliable capacity change detected'
    : `${analysis?.boundaries?.length ?? 0} reliable capacity changes detected`;
  if (analysis?.status === 'insufficient_evidence') return 'More completed reset windows needed';
  if (analysis?.status === 'missing') return 'Capacity analysis is queued';
  return 'No reliable capacity change detected';
}

function timelineExplanation(analysis: AllowanceAnalysisPayload | undefined, running: boolean): string {
  if (running) return 'The aggregate-only detector is testing completed-cycle boundaries for this data revision.';
  if (!analysis || analysis.status === 'missing') return 'Analysis starts automatically when this data revision is available.';
  if (analysis.status === 'insufficient_evidence') {
    return analysis.reason ?? 'There are not yet enough quality-approved reset windows on both sides of a boundary.';
  }
  return 'No boundary passed both the family-wise significance gate and the strong-effect gate. Rejected candidate values are intentionally hidden.';
}

function statusLabel(analysis: AllowanceAnalysisPayload | undefined): string {
  if (!analysis || analysis.status === 'missing') return 'Queued';
  if (analysis.status === 'insufficient_evidence') return 'Insufficient evidence';
  return 'No supported change';
}

function formatCredits(value: number): string {
  return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)} credits / 1%`;
}

function formatSignedPercent(value: number): string {
  const formatted = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(Math.abs(value));
  return `${value > 0 ? '+' : value < 0 ? '−' : ''}${formatted}%`;
}

function formatDate(value: string): string {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp)
    ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }).format(timestamp)
    : value;
}

function formatDateTime(value: string): string {
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp)
    ? new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(timestamp)
    : value;
}
