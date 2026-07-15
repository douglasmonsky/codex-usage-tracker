import type {
  AllowanceAnalysisPayload,
  AllowanceSeriesPayload,
} from '../../api/allowanceIntelligenceTypes';
import styles from './AllowanceCapacityMethodology.module.css';

type AllowanceCapacityMethodologyProps = {
  series: AllowanceSeriesPayload;
  analysis: AllowanceAnalysisPayload | undefined;
};

export function AllowanceCapacityMethodology({
  series,
  analysis,
}: AllowanceCapacityMethodologyProps) {
  const parameters = analysis?.parameters;
  const chartPoints = series.capacity_history.eligible_cycle_count ?? 0;
  const eligible = analysis?.eligible_cycle_count
    ?? chartPoints
    ?? 0;
  const excluded = analysis?.excluded_cycle_count ?? 0;
  const candidates = analysis?.candidate_count ?? 0;
  const supported = analysis?.boundaries?.length ?? 0;
  return (
    <section className={styles.methodology} aria-labelledby="capacity-methodology-title">
      <div className={styles.methodologyHeader}>
        <div>
          <p className={styles.eyebrow}>Methodology</p>
          <h3 id="capacity-methodology-title">How to read and trust this chart</h3>
        </div>
        <p>{analysisConclusion(analysis, supported)}</p>
      </div>

      <div className={styles.methodologyGrid}>
        <section>
          <h4>What each mark means</h4>
          <ul>
            <li><strong>Dot + thin trace:</strong> quality-approved weekly reset identities, connected only within the same observed subscription plan.</li>
            <li><strong>Value:</strong> Locally priced credits ÷ visible percentage-point movement within that reset window.</li>
            <li><strong>Thick line:</strong> trailing 8-reset-window median calculated separately for each plan after 4 eligible windows. A middle-50% band appears when one plan is in view.</li>
            <li>Extreme points may be visually clipped in the robust view; their exact values stay in the table and full-range view.</li>
          </ul>
        </section>

        <section>
          <h4>Which evidence counts</h4>
          <ul>
            <li>Observations with the same reset timestamp are coalesced, even when sessions are interleaved.</li>
            <li>Plan labels come only from logged <code>plan_type</code> metadata; mixed and unknown windows remain explicit.</li>
            <li>Only high- or medium-quality completed windows with no conflicts and at least 95% priced-credit coverage count.</li>
            <li>Copied clone rows are excluded through canonical usage deduplication ({series.quality.copied_rows_excluded} excluded here).</li>
            <li>Reversals are censored. Raw prompts and transcript content are never used.</li>
          </ul>
        </section>

        <section>
          <h4>When a change is called reliable</h4>
          <ul>
            <li>Candidate boundaries are tested only within one continuous observed plan segment, with at least {parameters?.min_cycles_per_regime ?? '—'} reset windows on each side. A subscription switch is never called a capacity change.</li>
            <li>The detector evaluates up to {formatInteger(parameters?.permutation_count)} cycle-block permutations (or exact enumeration when bounded) and applies a {formatPercent(parameters?.familywise_alpha)} family-wise false-positive limit.</li>
            <li>A boundary must also have a strong effect: absolute Cliff&rsquo;s delta of at least 0.474.</li>
            <li>The corrected p-value and its Monte Carlo uncertainty must both clear the gate. Zero, one, or multiple changes can be supported.</li>
          </ul>
        </section>
      </div>

      <dl className={styles.methodologyEvidence} aria-label="Current chart evidence">
        <div><dt>Chart range</dt><dd>{chartPoints} reset windows</dd></div>
        <div><dt>Analysis scope</dt><dd>{eligible} eligible</dd></div>
        <div><dt>Eligibility filter</dt><dd>{excluded} excluded</dd></div>
        <div><dt>Boundary scan</dt><dd>{candidates} candidates tested</dd></div>
        <div><dt>Result</dt><dd>{supported} supported {supported === 1 ? 'change' : 'changes'}</dd></div>
      </dl>
    </section>
  );
}

function analysisConclusion(
  analysis: AllowanceAnalysisPayload | undefined,
  supported: number,
): string {
  if (!analysis || analysis.status === 'missing') {
    return 'The current revision has not been analyzed yet.';
  }
  if (analysis.status === 'insufficient_evidence') {
    return 'There are not yet enough quality-approved reset windows to test a boundary.';
  }
  if (supported > 0) {
    return `${supported} boundary ${supported === 1 ? 'meets' : 'boundaries meet'} every reliability gate.`;
  }
  return 'No candidate cleared both the selection-adjusted significance and strong-effect gates.';
}

function formatInteger(value: number | undefined): string {
  return typeof value === 'number' ? new Intl.NumberFormat().format(value) : '—';
}

function formatPercent(value: number | undefined): string {
  return typeof value === 'number'
    ? new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 }).format(value)
    : '—';
}
