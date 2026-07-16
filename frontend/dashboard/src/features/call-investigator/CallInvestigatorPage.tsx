import { ArrowLeft, ChevronLeft, ChevronRight, Copy, LockKeyhole, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import { callReturnViewFromSearch, clearInactiveViewSearchParams } from '../../app/shellUrl';
import { loadCallDetail, type CallDetailResult } from '../../api/calls';
import { enableContextApi, loadCallContext, type ContextRequestOptions } from '../../api/context';
import type { CallContextEntry, CallContextPayload, CallRow, ContextRuntime, DashboardModel } from '../../api/types';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { serviceTierDetail } from '../calls/serviceTier';
import { CallCacheDelta } from '../shared/CallCacheDelta';
import { CallDecisionCard } from '../shared/CallDecisionCard';
import { ContextAttributionModule } from '../shared/ContextAttributionModule';
import { ContextEntryMetadata } from '../shared/ContextEntryMetadata';
import { CallSourceMetadata } from '../shared/CallSourceMetadata';
import { TokenPricingBreakdown } from '../shared/TokenPricingBreakdown';
import { ThreadCallTimeline } from '../shared/ThreadCallTimeline';
import { cacheState, contextWindowLabel, sourceLine, summarizeTopCounts } from '../shared/callPresentation';
import { copyText } from '../shared/copyText';
import { CallSignalPucks } from '../shared/tables';
import {
  cachedCallContext,
  cachedContextEntryOpenKeys,
  cachedContextEntryShowAll,
  cachedContextEntryScrollTop,
  cachedContextOptions,
  contextEntryKey,
  rememberCallContext,
  rememberContextEntryOpen,
  rememberContextEntryShowAll,
  rememberContextEntryScrollTop,
  rememberContextOptions,
} from '../shared/contextEvidenceCache';
import {
  applyContextOptionsToUrl,
  contextErrorMessage as errorMessage,
  contextEvidenceNotes,
  contextOptionsFromSearch,
  contextRuntimeMessage,
  defaultContextOptions,
  olderContextOptions,
  type ContextLoadState,
} from '../shared/contextEvidenceState';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import {
  evidenceStateReadout,
  exactReadoutBody,
  nextDiagnosticMove,
  previousCallReadout,
  previousUnavailableReadout,
  readoutPositionDetail,
} from './callInvestigatorReadout';
import { resolveCallInvestigatorSelection } from './callInvestigatorState';

type CallInvestigatorPageProps = {
  model: DashboardModel;
  recordId: string;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
  onNavigateRecord: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  onBackToCalls: () => void;
  backLabel: string;
};

type DetailLoadState =
  | { status: 'idle' }
  | { status: 'loading'; recordId: string; message: string }
  | { status: 'loaded'; recordId: string; detail: CallDetailResult }
  | { status: 'error'; recordId: string; message: string };

export function CallInvestigatorPage({
  model,
  recordId,
  contextRuntime,
  onContextApiEnabledChange,
  onNavigateRecord,
  onCopyCallLink,
  onBackToCalls,
  backLabel,
}: CallInvestigatorPageProps) {
  const shellI18n = useShellI18n();
  const [copyStatus, setCopyStatus] = useState('');
  const [detailState, setDetailState] = useState<DetailLoadState>({ status: 'idle' });
  const [evidenceReadoutState, setEvidenceReadoutState] = useState<ContextLoadState>({ status: 'idle' });
  const [fullAnalysisRequest, setFullAnalysisRequest] = useState({ recordId: '', nonce: 0 });
  const loadedDetail = detailState.status === 'loaded' && detailState.recordId === recordId ? detailState.detail : null;
  const { modelIndex, hydratedDetail, call, previous, next, threadCalls, positionLabel } = useMemo(
    () => resolveCallInvestigatorSelection({ calls: model.calls, recordId, detail: loadedDetail }),
    [loadedDetail, model.calls, recordId],
  );
  const evidencePayload = evidenceReadoutState.status === 'loaded' ? evidenceReadoutState.payload : null;

  useEffect(() => {
    setEvidenceReadoutState({ status: 'idle' });
  }, [recordId]);

  useEffect(() => {
    if (!recordId || modelIndex >= 0) {
      setDetailState({ status: 'idle' });
      return;
    }
    if (contextRuntime.fileMode || !contextRuntime.apiToken) {
      setDetailState({
        status: 'error',
        recordId,
        message: 'This call is outside the loaded snapshot. Serve the dashboard with its localhost API token to hydrate it.',
      });
      return;
    }

    let cancelled = false;
    setDetailState({ status: 'loading', recordId, message: 'Loading call detail from localhost...' });
    loadCallDetail(recordId, contextRuntime)
      .then(detail => {
        if (!cancelled) {
          setDetailState({ status: 'loaded', recordId, detail });
        }
      })
      .catch(error => {
        if (!cancelled) {
          setDetailState({ status: 'error', recordId, message: errorMessage(error) });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [contextRuntime, modelIndex, recordId]);

  if (!call) {
    const message =
      detailState.status === 'loading' || detailState.status === 'error'
        ? detailState.message
        : recordId
          ? 'Selected call is not present in the loaded dashboard rows.'
          : 'No aggregate call rows are loaded.';
    return (
      <div className="page-grid">
        <div className="page-title-row">
          <div>
            <h1>Call Investigator</h1>
            <p>{message}</p>
          </div>
          <button className="toolbar-button" type="button" onClick={onBackToCalls}>
            <ArrowLeft size={16} /> {backLabel}
          </button>
        </div>
      </div>
    );
  }

async function copyLink() {
try {
const url = new URL(window.location.href);
clearInactiveViewSearchParams(url, 'call', callReturnViewFromSearch(url.search));
const copied = await copyText(url.toString());
if (!copied) {
throw new Error('Clipboard unavailable');
}
      setCopyStatus('Copied investigator link');
    } catch {
      setCopyStatus('Copy unavailable in this browser');
    }
  }

  return (
    <div className="call-investigator-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Call Investigator</h1>
          <p>{call.thread} / {call.model}</p>
        </div>
        <div className="toolbar">
          <button className="toolbar-button" type="button" onClick={onBackToCalls}>
            <ArrowLeft size={16} /> {backLabel}
          </button>
          <button className="toolbar-button" type="button" onClick={() => previous && onNavigateRecord(previous.id)} disabled={!previous}>
            <ChevronLeft size={16} /> {shellI18n.t('button.previous_call', 'Previous call')}
          </button>
          <button className="toolbar-button" type="button" onClick={() => next && onNavigateRecord(next.id)} disabled={!next}>
            {shellI18n.t('button.next_call', 'Next call')} <ChevronRight size={16} />
          </button>
<button className="toolbar-button" type="button" onClick={copyLink} aria-label={shellI18n.t('button.copy_investigator_link', 'Copy investigator link')}>
<Copy size={16} /> {shellI18n.t('button.copy_link', 'Copy link')}
</button>
        </div>
      </div>

      <Panel
        title={shellI18n.t('call.readout.title', 'Investigation Readout')}
        subtitle={copyStatus || positionLabel}
        className="span-all"
        action={<StatusBadge label={shellI18n.t('call.readout.badge', 'Aggregate + on-demand evidence')} tone="blue" />}
      >
        <div className="call-summary">
          <StatusBadge label="Aggregate only" tone="green" />
          {hydratedDetail ? <StatusBadge label="Hydrated live" tone="blue" /> : null}
          <CallSignalPucks call={call} />
          <StatusBadge label="Raw context gated" tone="blue" />
        <span className="call-id">{call.id.slice(0, 16)}</span>
      </div>
      <InvestigationReadoutCards
        call={call}
        previous={previous}
        evidenceState={evidenceReadoutState}
        positionLabel={positionLabel}
      />
      <div className="drilldown-metric-grid wide">
          <InvestigatorMetric label="Total tokens" value={formatNumber(call.totalTokens)} detail={`${formatCompact(call.input)} input`} />
          <InvestigatorMetric label="Uncached input" value={formatNumber(call.uncachedInput)} detail="fresh billed input" />
          <InvestigatorMetric label="Cache hit rate" value={pct(call.cachedPct)} detail={cacheState(call)} />
          <InvestigatorMetric label="Estimated cost" value={money(call.cost)} detail={call.pricingEstimated ? 'estimated pricing' : 'configured pricing'} />
          <InvestigatorMetric label="Duration" value={call.duration} detail={serviceTierDetail(call)} />
<InvestigatorMetric label="Usage credits" value={call.credits ? call.credits.toFixed(3) : '-'} detail={call.usageCreditConfidence} />
</div>
<CallDecisionCard call={call} />
</Panel>

      <Panel title="Token Accounting" subtitle="Exact aggregate row fields">
        <TokenComposition call={call} />
        <TokenPricingBreakdown call={call} />
      </Panel>

      <Panel title="Cache Accounting" subtitle="Derived from adjacent aggregate call">
        <CallCacheDelta call={call} calls={threadCalls} />
      </Panel>

      <Panel title="Context Attribution" subtitle="Estimated from visible log volume" className="span-all">
        <ContextAttributionModule
          call={call}
          payload={evidencePayload}
          onRunFullAnalysis={() => setFullAnalysisRequest(current => ({ recordId: call.id, nonce: current.nonce + 1 }))}
          showHeading={false}
        />
      </Panel>

      <Panel title="Aggregate Identity" subtitle="Local metadata only">
        <dl className="detail-list">
          <DetailRow label="Record id" value={call.id} />
          <DetailRow label="Time" value={call.time} />
<DetailRow label="Thread" value={call.thread} />
	<DetailRow label="Model" value={call.model} />
	<DetailRow label="Effort" value={call.effort} />
	<DetailRow label="Project" value={call.project || 'Unknown'} />
	<DetailRow label="Context window" value={contextWindowLabel(call)} />
	<DetailRow label="Recommendation" value={call.recommendation || 'No aggregate recommendation'} />
	</dl>
        <CallSourceMetadata call={call} />
	        {call.recommendation ? (
	          <div className="recommendation-box">
	            <ShieldCheck size={16} />
            <p>{call.recommendation}</p>
          </div>
        ) : null}
      </Panel>

      <Panel title="Thread Context" subtitle={`${threadCalls.length} loaded related calls`} className="span-all">
        <ThreadContextPanel
          call={call}
          calls={threadCalls}
          onNavigateRecord={onNavigateRecord}
          onCopyCallLink={onCopyCallLink}
        />
      </Panel>

      <Panel title="Raw Evidence" subtitle="Explicit localhost request only" className="span-all">
        <InvestigatorEvidence
          key={call.id}
          call={call}
          contextRuntime={contextRuntime}
          onContextApiEnabledChange={onContextApiEnabledChange}
          onEvidenceStateChange={setEvidenceReadoutState}
          fullAnalysisRequestNonce={fullAnalysisRequest.recordId === call.id ? fullAnalysisRequest.nonce : 0}
        />
      </Panel>
    </div>
  );
}

function InvestigationReadoutCards({
  call,
  previous,
  evidenceState,
  positionLabel,
}: {
  call: CallRow;
  previous: CallRow | null;
  evidenceState: ContextLoadState;
  positionLabel: string;
}) {
const shellI18n = useShellI18n();
return (
<div className="investigation-readout-grid">
<ReadoutCard
        label={shellI18n.t('call.readout.exact_label', 'Exact callback accounting')}
        body={exactReadoutBody(call, shellI18n)}
      />
<ReadoutCard
        label={shellI18n.t('call.readout.previous_label', 'Compared previous call')}
        body={previous ? previousCallReadout(call, previous) : previousUnavailableReadout(shellI18n)}
      />
<ReadoutCard label={shellI18n.t('call.readout.evidence_label', 'Evidence state')} body={evidenceStateReadout(evidenceState, shellI18n)} />
<ReadoutCard label={shellI18n.t('call.readout.next_label', 'Next diagnostic move')} body={nextDiagnosticMove(call, previous)} detail={readoutPositionDetail(positionLabel)} />
</div>
);
}

function ReadoutCard({ label, body, detail }: { label: string; body: string; detail?: string }) {
return (
<div className="investigation-readout-card">
<span>{label}</span>
<p>{body}</p>
      {detail ? <small>{detail}</small> : null}
    </div>
);
}

function InvestigatorEvidence({
  call,
  contextRuntime,
  onContextApiEnabledChange,
  onEvidenceStateChange,
  fullAnalysisRequestNonce,
}: {
  call: CallRow;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
  onEvidenceStateChange: (state: ContextLoadState) => void;
  fullAnalysisRequestNonce: number;
}) {
  const shellI18n = useShellI18n();
  const [options, setOptions] = useState(() => contextOptionsFromSearch(window.location.search, cachedContextOptions(call.id) ?? defaultContextOptions));
  const [contextState, setContextState] = useState<ContextLoadState>({ status: 'idle' });
  const canUseContextServer = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const canLoadContext = canUseContextServer && contextRuntime.contextApiEnabled;

  useEffect(() => {
    const cached = cachedCallContext(call.id, options);
    setContextState(cached ? { status: 'loaded', payload: cached } : { status: 'idle' });
  }, [call.id, options.includeToolOutput, options.includeCompactionHistory, options.maxChars, options.maxEntries, options.mode]);

  useEffect(() => {
    onEvidenceStateChange(contextState);
  }, [contextState, onEvidenceStateChange]);

  useEffect(() => {
if (fullAnalysisRequestNonce <= 0 || !canLoadContext || contextState.status === 'loading') return;
const nextOptions: ContextRequestOptions = { ...options, mode: 'full' };
applyContextOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading full turn analysis...');
  }, [fullAnalysisRequestNonce]);

  async function enableContextLoading() {
    setContextState({ status: 'loading', message: 'Enabling localhost context API...' });
    try {
      const enabled = await enableContextApi(contextRuntime);
      onContextApiEnabledChange(enabled);
      setContextState({
        status: 'idle',
        message: enabled ? 'Context API enabled. Load this call when ready.' : 'Context API did not enable.',
      });
    } catch (error) {
      setContextState({ status: 'error', message: errorMessage(error) });
    }
  }

  async function loadEvidence(nextOptions: ContextRequestOptions = options, message = 'Loading selected-turn evidence...') {
    rememberContextOptions(call.id, nextOptions);
    const cached = cachedCallContext(call.id, nextOptions);
    if (cached) {
      setContextState({ status: 'loaded', payload: cached });
      return;
    }
    setContextState({ status: 'loading', message });
    try {
      const payload = await loadCallContext(call.id, contextRuntime, nextOptions);
      rememberCallContext(call.id, nextOptions, payload);
      setContextState({ status: 'loaded', payload });
    } catch (error) {
      setContextState({ status: 'error', message: errorMessage(error) });
    }
  }

  function loadFullAnalysis() {
if (!canLoadContext || contextState.status === 'loading') return;
const nextOptions: ContextRequestOptions = { ...options, mode: 'full' };
applyContextOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading full turn analysis...');
  }

function loadOlderContext(payload: CallContextPayload) {
const nextOptions = olderContextOptions(payload, options);
applyContextOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading older context...');
}

function loadToolOutput() {
const nextOptions: ContextRequestOptions = { ...options, includeToolOutput: true };
applyContextOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading omitted tool output...');
}

function loadCompactionHistory() {
const nextOptions: ContextRequestOptions = { ...options, includeCompactionHistory: true };
applyContextOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading compacted replacement...');
}

  function applyContextOptions(nextOptions: ContextRequestOptions) {
setOptions(nextOptions);
rememberContextOptions(call.id, nextOptions);
const url = new URL(window.location.href);
applyContextOptionsToUrl(url, nextOptions);
window.history.replaceState(null, '', url);
}

function updateOption<K extends keyof ContextRequestOptions>(key: K, value: ContextRequestOptions[K]) {
setOptions(current => {
const next = { ...current, [key]: value };
rememberContextOptions(call.id, next);
const url = new URL(window.location.href);
applyContextOptionsToUrl(url, next);
window.history.replaceState(null, '', url);
return next;
});
  }

  return (
    <div className="investigator-evidence">
      <div className="locked-context-card">
        <LockKeyhole size={20} />
        <div>
          <strong>Raw context is gated</strong>
          <p>{contextRuntimeMessage(contextRuntime)}</p>
        </div>
      </div>
      <div className="context-action-grid">
        <button
          className="toolbar-button"
          type="button"
          onClick={enableContextLoading}
          disabled={!canUseContextServer || contextRuntime.contextApiEnabled || contextState.status === 'loading'}
        >
        {shellI18n.t('button.enable_context_loading', 'Enable context loading')}
        </button>
<button
className="primary-button"
type="button"
onClick={() => loadEvidence()}
disabled={!canLoadContext || contextState.status === 'loading'}
>
{shellI18n.t('button.show_turn_evidence', 'Show turn log evidence')}
</button>
<button
className="toolbar-button"
type="button"
onClick={loadFullAnalysis}
disabled={!canLoadContext || contextState.status === 'loading'}
>
{shellI18n.t('button.full_serialized_analysis', 'Run full serialized analysis')}
</button>
<label className="context-field">
<span>Mode</span>
<select
aria-label="Context mode"
value={options.mode}
disabled={!canLoadContext || contextState.status === 'loading'}
onChange={event => updateOption('mode', event.target.value === 'full' ? 'full' : 'quick')}
>
<option value="quick">Quick</option>
<option value="full">Full</option>
</select>
</label>
<label className="context-field">
<span>Entries</span>
<select
aria-label="Context entries"
value={String(options.maxEntries)}
disabled={!canLoadContext || contextState.status === 'loading'}
onChange={event => updateOption('maxEntries', Number(event.target.value))}
>
<option value="20">20</option>
<option value="50">50</option>
<option value="100">100</option>
<option value="0">All</option>
</select>
</label>
<label className="toggle-row">
<input
type="checkbox"
checked={options.includeToolOutput}
disabled={!canLoadContext || contextState.status === 'loading'}
            onChange={event => updateOption('includeToolOutput', event.target.checked)}
/>
{shellI18n.t('button.include_tool_output', 'Include tool output')}
</label>
<label className="toggle-row">
<input
type="checkbox"
checked={options.includeCompactionHistory}
disabled={!canLoadContext || contextState.status === 'loading'}
onChange={event => updateOption('includeCompactionHistory', event.target.checked)}
/>
Include compaction history
</label>
<label className="toggle-row">
<input
type="checkbox"
            checked={options.maxChars === 0}
            disabled={!canLoadContext || contextState.status === 'loading'}
            onChange={event => updateOption('maxChars', event.target.checked ? 0 : defaultContextOptions.maxChars)}
          />
 {shellI18n.t('button.no_char_limit', 'No char limit')}
        </label>
      </div>
      {contextState.status === 'idle' && contextState.message ? <p className="context-state-note">{contextState.message}</p> : null}
      {contextState.status === 'loading' ? <p className="context-state-note">{contextState.message}</p> : null}
      {contextState.status === 'error' ? <p className="context-state-note error">{contextState.message}</p> : null}
      {contextState.status === 'loaded' ? (
        <ContextEvidence
          payload={contextState.payload}
          onLoadOlder={loadOlderContext}
          onLoadCompactionHistory={loadCompactionHistory}
          onLoadToolOutput={loadToolOutput}
        />
      ) : null}
      <p className="privacy-note">
        Raw context is read from the local JSONL source only after this explicit action and is not embedded in static dashboard HTML.
      </p>
    </div>
  );
}

function ContextEvidence({
payload,
onLoadOlder,
onLoadCompactionHistory,
onLoadToolOutput,
}: {
payload: CallContextPayload;
onLoadOlder: (payload: CallContextPayload) => void;
onLoadCompactionHistory: () => void;
onLoadToolOutput: () => void;
}) {
const shellI18n = useShellI18n();
const entries = payload.entries ?? [];
const omitted = payload.omitted ?? {};
  const olderEntries = Number(omitted.older_entries ?? 0);
  const notes = contextEvidenceNotes(payload);
  const initialEntryLimit = 10;
  const recordId = String(payload.record_id ?? '');
  const [showAllEntries, setShowAllEntries] = useState(() => cachedContextEntryShowAll(recordId));
  const [openEntryKeys, setOpenEntryKeys] = useState<Set<string>>(() => cachedContextEntryOpenKeys(recordId, entries));
  useEffect(() => {
    setShowAllEntries(cachedContextEntryShowAll(recordId));
    setOpenEntryKeys(cachedContextEntryOpenKeys(recordId, entries));
  }, [
    entries.length,
    payload.context_mode,
    payload.include_compaction_history,
    payload.include_tool_output,
    payload.omitted?.max_chars,
    payload.omitted?.max_entries,
    payload.record_id,
    recordId,
  ]);
  const visibleEntries = showAllEntries ? entries : entries.slice(0, initialEntryLimit);
  const hiddenEntryCount = Math.max(entries.length - visibleEntries.length, 0);
  function toggleShowAllEntries() {
    setShowAllEntries(current => {
      const next = !current;
      rememberContextEntryShowAll(recordId, next);
      return next;
    });
  }
  function rememberEntryOpen(key: string, open: boolean) {
    rememberContextEntryOpen(recordId, key, open);
    setOpenEntryKeys(current => {
      const next = new Set(current);
      if (open) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  }

  return (
<div className="context-evidence">
<div className="context-evidence-summary">
<InvestigatorMetric label="Entries" value={formatNumber(entries.length)} detail={String(payload.context_mode ?? 'quick')} />
<InvestigatorMetric label="Visible chars" value={formatNumber(Number(payload.visible_char_count ?? 0))} detail="redacted local text" />
<InvestigatorMetric label="Visible tokens" value={formatNumber(Number(payload.visible_token_estimate ?? 0))} detail="estimator" />
<InvestigatorMetric label="Older omitted" value={formatNumber(olderEntries)} detail="entry budget" />
</div>
{notes.length ? <p className="context-note">{notes.join(' ')}</p> : null}
{olderEntries > 0 ? (
<div className="context-followup-actions">
<button className="toolbar-button" type="button" onClick={() => onLoadOlder(payload)}>
{shellI18n.t('button.load_older_context', 'Load older entries')}
</button>
</div>
) : null}
<div className="context-entry-list">
        {visibleEntries.map((entry, index) => {
          const key = contextEntryKey(entry, index);
          return (
          <details
            className="context-entry"
            key={key}
            open={openEntryKeys.has(key)}
            onToggle={event => rememberEntryOpen(key, event.currentTarget.open)}
          >
            <summary className="context-entry-summary">
              <div className="context-entry-meta">
                <strong>{entry.label || entry.role || entry.type || `Entry ${index + 1}`}</strong>
<span>{entry.line_number ? `line ${entry.line_number}` : entry.timestamp || 'local evidence'}</span>
</div>
</summary>
<ContextEntryMetadata entry={entry} />
{entry.tool_output_omitted ? (
<div className="context-entry-actions">
<button className="toolbar-button" type="button" onClick={onLoadToolOutput}>
{shellI18n.t('button.show_tool_output', 'Show tool output')}
</button>
</div>
) : null}
            <ContextEntryCompaction entry={entry} onLoadCompactionHistory={onLoadCompactionHistory} />
            <pre
              ref={element => {
                if (element) element.scrollTop = cachedContextEntryScrollTop(recordId, key);
              }}
              onScroll={event => rememberContextEntryScrollTop(recordId, key, event.currentTarget.scrollTop)}
            >{entry.text || '[no visible text]'}</pre>
          </details>
          );
        })}
{!entries.length ? <p className="empty-state">No visible evidence entries returned for this call.</p> : null}
</div>
{entries.length > initialEntryLimit ? (
<div className="context-followup-actions">
<button className="toolbar-button" type="button" onClick={toggleShowAllEntries}>
{showAllEntries
? `Show first ${formatNumber(initialEntryLimit)} entries`
: `Show all ${formatNumber(entries.length)} returned entries`}
</button>
{!showAllEntries ? <span className="context-entry-count-note">{formatNumber(hiddenEntryCount)} entries hidden in compact view</span> : null}
</div>
) : null}
</div>
  );
}

function ContextEntryCompaction({
entry,
onLoadCompactionHistory,
}: {
entry: CallContextEntry;
onLoadCompactionHistory: () => void;
}) {
const shellI18n = useShellI18n();
const compaction = entry.compaction;
if (!compaction?.replacement_history_available) return null;
const replacementHistory = compaction.replacement_history ?? [];
const replacementCount = Number(compaction.replacement_entry_count ?? replacementHistory.length);

return (
<div className="context-entry-compaction">
<strong>Compaction detected</strong>
<span>{formatNumber(replacementCount)} replacement history entries available.</span>
{replacementHistory.length ? (
<div className="context-replacement-history" aria-label="Compacted replacement context">
{replacementHistory.map((item, index) => (
<div className="context-replacement-entry" key={`${item.label ?? 'replacement'}-${index}`}>
<strong>{item.label || `Replacement item ${index + 1}`}</strong>
<pre>{item.text || '[no visible replacement text]'}</pre>
</div>
))}
</div>
) : (
<div className="context-entry-actions">
<button className="toolbar-button" type="button" onClick={onLoadCompactionHistory}>
{shellI18n.t('button.show_compaction_history', 'Show compacted replacement')}
</button>
</div>
)}
</div>
);
}



function ThreadContextPanel({
  call,
  calls,
  onNavigateRecord,
  onCopyCallLink,
}: {
  call: CallRow;
  calls: CallRow[];
  onNavigateRecord: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const shellI18n = useShellI18n();
  const copyLinkLabel = shellI18n.t('button.copy_link', 'Copy link');
  const rows = calls.length ? calls : [call];
  const selectedIndex = Math.max(rows.findIndex(row => row.id === call.id), 0);
  const totalTokens = rows.reduce((sum, row) => sum + row.totalTokens, 0);
  const totalCost = rows.reduce((sum, row) => sum + row.cost, 0);
  const averageCache = rows.reduce((sum, row) => sum + row.cachedPct, 0) / Math.max(rows.length, 1);
  const contextPressure = rows.filter(row => Number(row.contextWindowPct ?? 0) >= 60).length;
  const cacheRisk = rows.filter(row => row.cachedPct < 25 || row.signal === 'cache-risk').length;

  return (
    <div className="thread-context-module">
      <div className="drilldown-metric-grid wide">
        <InvestigatorMetric label="Thread calls" value={formatNumber(rows.length)} detail={`selected ${selectedIndex + 1} of ${rows.length}`} />
        <InvestigatorMetric label="Thread tokens" value={formatCompact(totalTokens)} detail="loaded aggregate rows" />
        <InvestigatorMetric label="Thread cost" value={money(totalCost)} detail="estimated aggregate" />
          <InvestigatorMetric
            label="Avg cache"
            value={pct(averageCache)}
            detail={summarizeTopCounts(rows.map(row => row.model))}
          />
        <InvestigatorMetric label="Cache risks" value={formatNumber(cacheRisk)} detail="weak reuse or flagged" />
        <InvestigatorMetric label="Context pressure" value={formatNumber(contextPressure)} detail=">=60% context window" />
      </div>

      <div className="thread-context-grid">
        <div>
          <h3>Thread timeline</h3>
          <ThreadCallTimeline
            selectedCall={call}
            calls={rows}
            onOpenInvestigator={onNavigateRecord}
            onCopyCallLink={onCopyCallLink}
            className="investigator-thread-timeline"
            copyAriaContext="thread context call"
            copyLabel={copyLinkLabel}
          />
        </div>

        <dl className="detail-list compact">
          <DetailRow label="Project" value={call.project || 'Unknown'} />
          <DetailRow label="Project path" value={call.projectRelativeCwd || call.cwd || '.'} />
          <DetailRow label="Source line" value={sourceLine(call)} />
          <DetailRow label="Session" value={call.sessionId || 'Not available'} />
          <DetailRow label="Parent thread" value={call.parentThread || 'None'} />
        <DetailRow label="Models in thread" value={summarizeTopCounts(rows.map(row => row.model), { limit: 3 })} />
        <DetailRow label="Effort mix" value={summarizeTopCounts(rows.map(row => row.effort), { limit: 3 })} />
        </dl>
      </div>
    </div>
  );
}

function InvestigatorMetric({ label, value, detail }: { label: string; value: string; detail: string }) {
return (
<span className="drilldown-metric">
<small>{label}</small>
      <strong>{value}</strong>
      <em>{detail}</em>
</span>
);
}

function DetailRow({ label, value }: { label: string; value: string }) {
return (
<div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

function TokenComposition({ call }: { call: CallRow }) {
  const cachedInput = Math.max(call.input - call.uncachedInput, 0);
  const segments = [
    { label: 'Cached input', value: cachedInput, color: '#2563eb' },
    { label: 'Uncached input', value: call.uncachedInput, color: '#f59e0b' },
    { label: 'Output', value: call.output, color: '#059669' },
    { label: 'Reasoning', value: call.reasoningOutput, color: '#7c3aed' },
  ].filter(segment => segment.value > 0);
  const total = Math.max(segments.reduce((sum, segment) => sum + segment.value, 0), 1);

  return (
    <div className="composition-card">
      <div className="composition-head">
        <strong>Token composition</strong>
        <span>{formatCompact(total)} visible tokens</span>
      </div>
      <div className="composition-bar" role="img" aria-label="Token composition">
        {segments.map(segment => (
          <i key={segment.label} style={{ width: `${Math.max(segment.value / total * 100, 3)}%`, background: segment.color }} />
        ))}
      </div>
      <div className="composition-legend">
        {segments.map(segment => (
          <span key={segment.label}>
            <i style={{ background: segment.color }} />
            {segment.label}
          </span>
        ))}
      </div>
    </div>
  );
}
