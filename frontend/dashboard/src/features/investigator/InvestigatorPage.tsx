import { useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  Download,
  FlaskConical,
  RefreshCw,
  Search,
  Settings,
  ShieldCheck,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import {
  diagnosticSnapshotDefinitions,
} from '../../api/diagnostics';
import {
  type InvestigationWalkBranch,
} from '../../api/investigations';
import type { CallRow, ContextRuntime, DashboardModel } from '../../api/types';
import { buildDashboardTarget } from '../../app/dashboardTargets';
import { useShellI18n } from '../../app/i18nContext';
import {
  currentDashboardServiceOrigin,
  DashboardEvidenceActions,
} from '../../components/DashboardEvidenceActions';
import { FeatureMaturityBanner } from '../../components/FeatureMaturityBanner';
import {
  investigatorWalkQueryOptions,
} from '../../data/investigatorQueries';
import { Button, MetricReadout, PageLoadProgress, StatusBadge, Surface } from '../../design';
import type { DashboardViewId } from '../../routes/dashboardSearch';
import { Visualization } from '../../visualization';
import { fallbackDiagnosticSnapshots } from '../diagnostics/diagnosticSnapshotFallbacks';
import { csvDateStamp } from '../shared/exportCsv';
import { formatCompact } from '../shared/format';
import answerStyles from './InvestigationAnswer.module.css';
import { InvestigationEvidenceLedger } from './InvestigationEvidenceLedger';
import traceStyles from './InvestigationTrace.module.css';
import {
  buildInvestigationWorkspace,
  buildWasteFingerprintSpec,
  callsForFinding,
  type InvestigationFinding,
  type InvestigationTone,
} from './investigationModel';
import styles from './InvestigatorPage.module.css';
import { useInvestigatorEvidence } from './useInvestigatorEvidence';

type InvestigatorPageProps = {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  includeArchived?: boolean;
  sourceKey?: string;
  sourceRevision?: string;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  onNavigateView: (view: DashboardViewId) => void;
};

const defaultQuestion = 'Where is avoidable token waste concentrated?';

export function investigatorCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  const rank = Number(new URLSearchParams(window.location.search).get('finding') ?? '');
  const finding = model.findings.find(candidate => candidate.rank === rank) ?? model.findings[0];
  return finding ? callsForFinding(finding, model.calls) : topCalls(model.calls, 8);
}

export function InvestigatorPage({
  model,
  contextRuntime,
  includeArchived = false,
  sourceKey,
  sourceRevision = '',
  onOpenInvestigator,
  onCopyCallLink,
  onNavigateView,
}: InvestigatorPageProps) {
  const i18n = useShellI18n();
  const canUseLive = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const fallbackSnapshots = useMemo(() => fallbackDiagnosticSnapshots(model), [model]);
  const evidence = useInvestigatorEvidence({
    canUseLive,
    contextRuntime,
    includeArchived,
    sourceKey,
    sourceRevision,
  });
  const effectiveSnapshots = canUseLive
    ? { ...fallbackSnapshots, ...evidence.liveSnapshots }
    : fallbackSnapshots;
  const workspace = useMemo(
    () => buildInvestigationWorkspace(model, evidence.agenticQuery.data, effectiveSnapshots),
    [evidence.agenticQuery.data, effectiveSnapshots, model],
  );
  const requestedFinding = readFindingParam();
  const [selectedId, setSelectedId] = useState(requestedFinding);
  const selected = resolveSelectedFinding(workspace.findings, selectedId || requestedFinding);
  const [question, setQuestion] = useState(defaultQuestion);
  const [refreshing, setRefreshing] = useState(false);
  const [statusMessage, setStatusMessage] = useState('Stored diagnostics ready');
  const selectedRank = Math.max(1, selected ? workspace.findings.indexOf(selected) + 1 : 1);
  const selectedRecordId = selected?.evidence.find(row => row.recordId)?.recordId;
  const evidenceTarget = useMemo(
    () => investigatorEvidenceDashboardTarget(
      selectedRecordId,
      includeArchived,
      currentDashboardServiceOrigin(),
    ),
    [includeArchived, selectedRecordId],
  );
  const walkQuery = useQuery({
    ...investigatorWalkQueryOptions({
      runtime: contextRuntime,
      includeArchived,
      sourceKey,
      sourceRevision,
      question,
      evidenceLimit: 6,
    }),
    enabled: false,
  });
  const fingerprintSpec = useMemo(
    () => buildWasteFingerprintSpec(workspace.findings, includeArchived ? 'all' : 'active', sourceRevision),
    [includeArchived, sourceRevision, workspace.findings],
  );
  useEffect(() => {
    if (!selected && workspace.findings[0]) setSelectedId(workspace.findings[0].id);
  }, [selected, workspace.findings]);

  function selectFinding(finding: InvestigationFinding) {
    setSelectedId(finding.id);
    const url = new URL(window.location.href);
    url.searchParams.set('view', 'investigator');
    url.searchParams.set('finding', finding.id);
    window.history.replaceState(null, '', url);
    setStatusMessage(`Selected ${finding.title}`);
  }

  function openThread(thread: string) {
    onNavigateView('threads');
    const url = new URL(window.location.href);
    url.searchParams.set('thread_q', thread);
    window.history.replaceState(null, '', url);
  }

  async function refreshEvidence() {
    if (!canUseLive || refreshing) return;
    setRefreshing(true);
    setStatusMessage('Refreshing investigation evidence...');
    try {
      const refreshedCount = await evidence.refresh();
      setStatusMessage(`Live evidence refreshed · ${refreshedCount} diagnostic modules`);
    } catch (error) {
      setStatusMessage(`Refresh failed: ${errorMessage(error)}`);
    } finally {
      setRefreshing(false);
    }
  }

  const refreshProgress = refreshing && evidence.refreshJob
    ? evidence.refreshJob.progress
    : null;
  const progressModules = refreshProgress
    ? evidence.modules.slice(1).map((module, index) => ({
        ...module,
        status: index < refreshProgress.completed_units ? 'ready' as const : 'updating' as const,
      }))
    : evidence.modules;

  function runLocalTrace() {
    if (!contextRuntime.contextApiEnabled) {
      onNavigateView('settings');
      return;
    }
    void walkQuery.refetch();
  }

  function exportEvidence() {
    downloadJson(`codex-investigation-${csvDateStamp()}.json`, {
      schema: 'codex-usage-dashboard-investigation-export-v1',
      generated_at: new Date().toISOString(),
      selected_finding: selected,
      findings: workspace.findings,
      caveats: workspace.caveats,
      local_trace: walkQuery.data,
      includes_raw_fragments: false,
    });
    setStatusMessage('Strict local evidence bundle exported');
  }

  if (!selected) {
    return <section className="route-state" role="status">No investigation evidence is available for the loaded scope.</section>;
  }

  return (
    <div className={styles.page}>
      <header className={styles.pageHeader}>
        <div>
          <p className={styles.eyebrow}>Root-cause workspace</p>
          <h1>Investigate</h1>
          <p>Ranked waste signals, linked evidence, and one explicit verification path.</p>
        </div>
        <div className={styles.headerActions}>
          <DashboardEvidenceActions
            target={evidenceTarget}
            question={`Investigate aggregate evidence for finding ${selectedRank}.`}
            onStatus={setStatusMessage}
          />
          <Button onClick={exportEvidence}><Download />Export evidence</Button>
          <Button variant="primary" onClick={refreshEvidence} disabled={!canUseLive || refreshing}>
            <RefreshCw />{refreshing ? 'Refreshing' : 'Refresh evidence'}
          </Button>
        </div>
      </header>

      <FeatureMaturityBanner
        kind="transitioning"
        title="Available during transition"
        description="This workspace remains available in Release N while its future placement is prepared."
        replacement={{
          operation: 'usage_analyze(goal="usage_spike") → usage_evidence',
          href: '?view=explore&mode=calls',
        }}
      />

      <PageLoadProgress
        active={canUseLive && (refreshing || evidence.modules.some(module => module.status === 'loading' || module.status === 'updating'))}
        completed={refreshProgress?.completed_units ?? evidence.progress.ready}
        total={refreshProgress?.total_units ?? evidence.progress.total}
        label={refreshing ? 'Refreshing investigation evidence' : 'Loading investigation evidence'}
        error={canUseLive ? evidence.progressError : null}
        modules={progressModules}
        updating={refreshing || evidence.modules.some(module => module.status === 'updating')}
      />

      <div className={styles.statusRow} role="status" aria-live="polite">
        <StatusBadge tone={workspace.live ? 'positive' : 'neutral'}>{workspace.live ? 'Live report services' : 'Loaded aggregate fallback'}</StatusBadge>
        <StatusBadge tone={evidence.loadingSnapshots ? 'caution' : 'context'}>
          {evidence.loadingSnapshots ? `Loading diagnostics ${evidence.loadedSnapshotCount}/${diagnosticSnapshotDefinitions.length}` : `${evidence.loadedSnapshotCount || diagnosticSnapshotDefinitions.length} diagnostic modules`}
        </StatusBadge>
        <span>{evidence.agenticQuery.isError ? `Live report unavailable: ${errorMessage(evidence.agenticQuery.error)}` : statusMessage}</span>
      </div>

      <section className={answerStyles.answerBand} data-tone={selected.tone} aria-labelledby="investigation-answer-title">
        <div className={answerStyles.answerCopy}>
          <span>Selected finding</span>
          <h2 id="investigation-answer-title">{i18n.translateText(selected.title)}</h2>
          <p>{i18n.translateText(selected.summary)}</p>
        </div>
        <div className={answerStyles.answerMetrics}>
          <MetricReadout label="Confidence" value={i18n.translateText(selected.confidence)} detail={i18n.translateText(selected.source)} />
          <MetricReadout label="Evidence" value={selected.evidenceCount.toLocaleString()} detail="Linked rows" />
          <MetricReadout label="Impact signal" value={formatCompact(selected.impactScore)} detail="Ranking score" />
        </div>
      </section>

      <div className={styles.analysisGrid}>
        <Surface className={styles.findingsPanel}>
          <div className={styles.panelHeader}>
            <div><h2>Ranked findings</h2><p>Confidence, scope, and evidence stay visible while comparing.</p></div>
            <StatusBadge tone="context">{i18n.translateText(`${workspace.findings.length} signals`)}</StatusBadge>
          </div>
          <div className={styles.findingList}>
            {workspace.findings.map(finding => (
              <button
                className={styles.findingButton}
                data-selected={finding.id === selected.id}
                key={finding.id}
                type="button"
                onClick={() => selectFinding(finding)}
              >
                <i className={styles.findingSignal} data-tone={finding.tone} aria-hidden="true" />
                <span className={styles.findingCopy}><strong>{i18n.translateText(finding.title)}</strong><span>{i18n.translateText(finding.category)}</span></span>
                <span className={styles.findingEvidence}>{finding.evidenceCount} rows</span>
                <ArrowRight aria-hidden="true" />
              </button>
            ))}
          </div>
        </Surface>

        <Surface tone="subtle" className={styles.recommendationPanel}>
          <div className={styles.panelHeader}>
            <div><h2>Recommended change</h2><p>Deterministic action from the selected evidence family.</p></div>
            <StatusBadge tone={toneToBadge(selected.tone)}>{selected.confidence}</StatusBadge>
          </div>
          <p className={styles.recommendation}>{i18n.translateText(selected.action)}</p>
          <dl className={styles.methodList}>
            <div><dt>Verify with</dt><dd>{selected.verification.join(', ') || 'linked evidence rows'}</dd></div>
            <div><dt>Missing access</dt><dd>{i18n.translateText(selected.missingAccess)}</dd></div>
            <div><dt>Privacy</dt><dd>{i18n.translateText(selected.privacyNote)}</dd></div>
          </dl>
          <Button variant="primary" onClick={() => selected.evidence[0]?.recordId && onOpenInvestigator(selected.evidence[0].recordId)} disabled={!selected.evidence.some(row => row.recordId)}>
            <Search />Verify in call
          </Button>
        </Surface>
      </div>

      <Surface className={styles.fingerprintPanel}>
        <Visualization
          spec={fingerprintSpec}
          height={Math.min(480, Math.max(300, workspace.findings.length * 34))}
          onSelectionChange={selection => {
            const findingId = selection.split(':')[0];
            const finding = workspace.findings.find(candidate => candidate.id === findingId);
            if (finding) selectFinding(finding);
          }}
        />
      </Surface>

      <section className={styles.ledgerSection}>
        <div className={styles.panelHeader}>
          <div><h2>Evidence ledger</h2><p>Each supported row opens the underlying call or thread.</p></div>
          <StatusBadge tone="positive">{i18n.translateText(`${selected.evidence.length} linked`)}</StatusBadge>
        </div>
        <InvestigationEvidenceLedger
          findingTitle={i18n.translateText(selected.title)}
          rows={selected.evidence}
          onOpenCall={onOpenInvestigator}
          onCopyCallLink={onCopyCallLink}
          onOpenThread={openThread}
        />
      </section>

      <Surface className={traceStyles.hypothesisPanel}>
        <div className={styles.panelHeader}>
          <div><h2>Local hypothesis trace</h2><p>Bounded pattern exploration over the local content/event index.</p></div>
          <StatusBadge tone={contextRuntime.contextApiEnabled ? 'positive' : 'neutral'}>
            {contextRuntime.contextApiEnabled ? 'Content access enabled' : 'Content access off'}
          </StatusBadge>
        </div>
        <div className={traceStyles.hypothesisControls}>
          <label>
            <span className="sr-only">Investigation question</span>
            <FlaskConical aria-hidden="true" />
            <input value={question} onChange={event => setQuestion(event.target.value)} />
          </label>
          <Button variant="primary" onClick={runLocalTrace} disabled={!canUseLive || walkQuery.isFetching}>
            {contextRuntime.contextApiEnabled ? <FlaskConical /> : <Settings />}
            {walkQuery.isFetching ? 'Testing' : contextRuntime.contextApiEnabled ? 'Test hypothesis' : 'Enable in Settings'}
          </Button>
        </div>
        {walkQuery.isError ? <p className={traceStyles.errorState}>Local trace failed: {errorMessage(walkQuery.error)}</p> : null}
        {walkQuery.data ? <TraceResults branches={walkQuery.data.branches} /> : null}
      </Surface>

      <details className={traceStyles.caveats}>
        <summary><ShieldCheck />Method and caveats</summary>
        <ul>{workspace.caveats.map(caveat => <li key={caveat}>{caveat}</li>)}</ul>
      </details>
    </div>
  );
}

export function investigatorEvidenceDashboardTarget(
  recordId: string | undefined,
  includeArchived: boolean,
  serviceOrigin: string | null,
) {
  const common = {
    history: includeArchived ? 'all' as const : 'active' as const,
    privacy_mode: 'strict' as const,
    service_origin: serviceOrigin,
  };
  if (recordId) {
    try {
      return buildDashboardTarget({ ...common, view: 'call', record_id: recordId });
    } catch {
      // Legacy aggregate rows may not yet carry a canonical record ID.
    }
  }
  return buildDashboardTarget({ ...common, view: 'investigator' });
}

function TraceResults({ branches }: { branches: InvestigationWalkBranch[] }) {
  const supported = branches.filter(branch => branch.status !== 'no_evidence');
  return supported.length ? (
    <div className={traceStyles.traceResults}>
      {supported.slice(0, 5).map((branch, index) => (
        <article key={`${branch.scan_type ?? 'branch'}-${index}`}>
          <StatusBadge tone={Number(branch.score ?? 0) >= 60 ? 'positive' : 'caution'}>{String(branch.status ?? 'evidence')}</StatusBadge>
          <strong>{String(branch.hypothesis ?? branch.scan_type ?? 'Local pattern')}</strong>
          <span>{Number(branch.score ?? 0).toLocaleString()} score</span>
        </article>
      ))}
    </div>
  ) : <p className={traceStyles.emptyState}>No supported local pattern met the current threshold.</p>;
}

function resolveSelectedFinding(findings: InvestigationFinding[], requested: string): InvestigationFinding | undefined {
  const direct = findings.find(finding => finding.id === requested);
  if (direct) return direct;
  const rank = Number(requested);
  return Number.isFinite(rank) && rank > 0 ? findings[rank - 1] ?? findings[0] : findings[0];
}

function readFindingParam(): string {
  return new URLSearchParams(window.location.search).get('finding') ?? '';
}

function topCalls(calls: CallRow[], limit: number): CallRow[] {
  return [...calls].sort((left, right) => right.totalTokens - left.totalTokens).slice(0, limit);
}

function toneToBadge(tone: InvestigationTone): 'neutral' | 'positive' | 'caution' | 'risk' | 'context' {
  return tone;
}

function downloadJson(filename: string, payload: unknown): void {
  const serialized = JSON.stringify(payload, null, 2);
  const blob = new Blob([serialized], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
