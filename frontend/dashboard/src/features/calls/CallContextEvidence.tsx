import { LockKeyhole } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useShellI18n } from '../../app/i18nContext';
import { enableContextApi, loadCallContext, type ContextRequestOptions } from '../../api/context';
import type { CallContextEntry, CallContextPayload, CallRow, ContextRuntime } from '../../api/types';
import { ContextAttributionModule } from '../shared/ContextAttributionModule';
import { ContextEntryMetadata } from '../shared/ContextEntryMetadata';
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
  contextErrorMessage as errorMessage,
  contextEvidenceNotes,
  contextRuntimeMessage,
  defaultContextOptions,
  olderContextOptions,
  type ContextLoadState,
} from '../shared/contextEvidenceState';
import { formatNumber } from '../shared/format';
import { DetailRow, DrillMetric } from './CallDetailPrimitives';

export function CallContextEvidence({
call,
  contextRuntime,
  onContextApiEnabledChange,
}: {
  call: CallRow;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
}) {
  const shellI18n = useShellI18n();
  const [options, setOptions] = useState(() => cachedContextOptions(call.id) ?? defaultContextOptions);
  const [contextState, setContextState] = useState<ContextLoadState>({ status: 'idle' });
  const canUseContextServer = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const canLoadContext = canUseContextServer && contextRuntime.contextApiEnabled;

  useEffect(() => {
    const cached = cachedCallContext(call.id, options);
    setContextState(cached ? { status: 'loaded', payload: cached } : { status: 'idle' });
  }, [call.id, options.includeCompactionHistory, options.includeToolOutput, options.maxChars, options.maxEntries, options.mode]);

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
const nextOptions: ContextRequestOptions = { ...options, mode: 'full' };
setOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading full turn analysis...');
}

function loadOlderContext(payload: CallContextPayload) {
const nextOptions = olderContextOptions(payload, options);
setOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading older context...');
}

function loadToolOutput() {
const nextOptions: ContextRequestOptions = { ...options, includeToolOutput: true };
setOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading omitted tool output...');
}

function loadCompactionHistory() {
const nextOptions: ContextRequestOptions = { ...options, includeCompactionHistory: true };
setOptions(nextOptions);
void loadEvidence(nextOptions, 'Loading compacted replacement...');
}

  function updateOption<K extends keyof ContextRequestOptions>(key: K, value: ContextRequestOptions[K]) {
    setOptions(current => {
      const next = { ...current, [key]: value };
      rememberContextOptions(call.id, next);
      return next;
    });
  }

  return (
    <>
      <div className="locked-context-card">
        <LockKeyhole size={20} />
        <div>
          <strong>Raw context is gated</strong>
          <p>{contextRuntimeMessage(contextRuntime)}</p>
        </div>
      </div>
      <dl className="detail-list">
        <DetailRow label="Record id" value={call.id} />
        <DetailRow label="Time" value={call.time} />
        <DetailRow label="Thread" value={call.thread} />
        <DetailRow label="Model" value={call.model} />
        <DetailRow label="Effort" value={call.effort} />
      </dl>
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
aria-label="Side panel context mode"
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
aria-label="Side panel context entries"
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
          call={call}
          payload={contextState.payload}
          onLoadOlder={loadOlderContext}
          onRunFullAnalysis={loadFullAnalysis}
          onLoadCompactionHistory={loadCompactionHistory}
          onLoadToolOutput={loadToolOutput}
        />
      ) : null}
      <p className="privacy-note">
        Raw context is never embedded in the dashboard HTML. This view reads the selected local JSONL turn only after an explicit request.
      </p>
    </>
  );
}

function ContextEvidence({
call,
payload,
onLoadOlder,
onRunFullAnalysis,
onLoadCompactionHistory,
onLoadToolOutput,
}: {
call: CallRow;
payload: CallContextPayload;
onLoadOlder: (payload: CallContextPayload) => void;
onRunFullAnalysis: () => void;
onLoadCompactionHistory: () => void;
onLoadToolOutput: () => void;
}) {
const shellI18n = useShellI18n();
const entries = payload.entries ?? [];
const omitted = payload.omitted ?? {};
  const olderEntries = Number(omitted.older_entries ?? 0);
  const notes = contextEvidenceNotes(payload);
  const initialEntryLimit = 8;
  const recordId = call.id || String(payload.record_id ?? '');
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
<DrillMetric label="Entries" value={formatNumber(entries.length)} detail={String(payload.context_mode ?? 'quick')} />
<DrillMetric label="Visible chars" value={formatNumber(Number(payload.visible_char_count ?? 0))} detail="redacted local text" />
<DrillMetric label="Visible tokens" value={formatNumber(Number(payload.visible_token_estimate ?? 0))} detail="estimator" />
<DrillMetric label="Older omitted" value={formatNumber(olderEntries)} detail="entry budget" />
</div>
{notes.length ? <p className="context-note">{notes.join(' ')}</p> : null}
<ContextAttributionModule call={call} payload={payload} onRunFullAnalysis={onRunFullAnalysis} />
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
<details className="context-entry" key={key} open={openEntryKeys.has(key)} onToggle={event => rememberEntryOpen(key, event.currentTarget.open)}>
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
