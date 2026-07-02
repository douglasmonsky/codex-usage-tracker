import { ArrowLeft, ChevronLeft, ChevronRight, Copy, LockKeyhole, ShieldCheck } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { enableContextApi, loadCallContext, type ContextRequestOptions } from '../../api/context';
import type { CallContextPayload, CallRow, ContextRuntime, DashboardModel } from '../../api/types';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { formatCompact, formatNumber, money, pct } from '../shared/format';

type CallInvestigatorPageProps = {
  model: DashboardModel;
  recordId: string;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
  onNavigateRecord: (recordId: string) => void;
  onBackToCalls: () => void;
};

type ContextLoadState =
  | { status: 'idle'; message?: string }
  | { status: 'loading'; message: string }
  | { status: 'loaded'; payload: CallContextPayload }
  | { status: 'error'; message: string };

const defaultContextOptions: ContextRequestOptions = {
  includeToolOutput: false,
  includeCompactionHistory: false,
  maxChars: 8_000,
  maxEntries: 20,
  mode: 'quick',
};

export function CallInvestigatorPage({
  model,
  recordId,
  contextRuntime,
  onContextApiEnabledChange,
  onNavigateRecord,
  onBackToCalls,
}: CallInvestigatorPageProps) {
  const selectedIndex = useMemo(() => {
    const index = model.calls.findIndex(call => call.id === recordId);
    return index >= 0 ? index : 0;
  }, [model.calls, recordId]);
  const call = model.calls[selectedIndex] ?? null;
  const previous = selectedIndex > 0 ? model.calls[selectedIndex - 1] : null;
  const next = selectedIndex < model.calls.length - 1 ? model.calls[selectedIndex + 1] : null;
  const [copyStatus, setCopyStatus] = useState('');

  if (!call) {
    return (
      <div className="page-grid">
        <div className="page-title-row">
          <div>
            <h1>Call Investigator</h1>
            <p>No aggregate call rows are loaded.</p>
          </div>
          <button className="toolbar-button" type="button" onClick={onBackToCalls}>
            <ArrowLeft size={16} /> Back to Calls
          </button>
        </div>
      </div>
    );
  }

  async function copyLink() {
    try {
      await navigator.clipboard?.writeText(window.location.href);
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
            <ArrowLeft size={16} /> Back to Calls
          </button>
          <button className="toolbar-button" type="button" onClick={() => previous && onNavigateRecord(previous.id)} disabled={!previous}>
            <ChevronLeft size={16} /> Previous
          </button>
          <button className="toolbar-button" type="button" onClick={() => next && onNavigateRecord(next.id)} disabled={!next}>
            Next <ChevronRight size={16} />
          </button>
          <button className="toolbar-button" type="button" onClick={copyLink}>
            <Copy size={16} /> Copy link
          </button>
        </div>
      </div>

      <Panel
        title="Investigation Readout"
        subtitle={copyStatus || `${selectedIndex + 1} of ${model.calls.length} loaded calls`}
        className="span-all"
        action={<StatusBadge label="Aggregate + on-demand evidence" tone="blue" />}
      >
        <div className="call-summary">
          <StatusBadge label="Aggregate only" tone="green" />
          <StatusBadge label={call.signal} tone={call.signal === 'cache-risk' ? 'orange' : 'blue'} />
          <StatusBadge label="Raw context gated" tone="blue" />
          <span className="call-id">{call.id.slice(0, 16)}</span>
        </div>
        <div className="drilldown-metric-grid wide">
          <InvestigatorMetric label="Total tokens" value={formatNumber(call.totalTokens)} detail={`${formatCompact(call.input)} input`} />
          <InvestigatorMetric label="Uncached input" value={formatNumber(call.uncachedInput)} detail="fresh billed input" />
          <InvestigatorMetric label="Cache hit rate" value={pct(call.cachedPct)} detail={cacheState(call)} />
          <InvestigatorMetric label="Estimated cost" value={money(call.cost)} detail={call.pricingEstimated ? 'estimated pricing' : 'configured pricing'} />
          <InvestigatorMetric label="Duration" value={call.duration} detail={call.fast ? 'fast candidate' : 'normal throughput'} />
          <InvestigatorMetric label="Usage credits" value={call.credits ? call.credits.toFixed(3) : '-'} detail={call.usageCreditConfidence} />
        </div>
      </Panel>

      <Panel title="Token Accounting" subtitle="Exact aggregate row fields">
        <TokenComposition call={call} />
        <dl className="detail-list">
          <DetailRow label="Input tokens" value={formatNumber(call.input)} />
          <DetailRow label="Uncached input" value={formatNumber(call.uncachedInput)} />
          <DetailRow label="Output tokens" value={formatNumber(call.output)} />
          <DetailRow label="Reasoning output" value={formatNumber(call.reasoningOutput)} />
          <DetailRow label="Total tokens" value={formatNumber(call.totalTokens)} />
        </dl>
      </Panel>

      <Panel title="Aggregate Identity" subtitle="Local metadata only">
        <dl className="detail-list">
          <DetailRow label="Record id" value={call.id} />
          <DetailRow label="Time" value={call.time} />
          <DetailRow label="Thread" value={call.thread} />
          <DetailRow label="Model" value={call.model} />
          <DetailRow label="Effort" value={call.effort} />
          <DetailRow label="Recommendation" value={call.recommendation || 'No aggregate recommendation'} />
        </dl>
        {call.recommendation ? (
          <div className="recommendation-box">
            <ShieldCheck size={16} />
            <p>{call.recommendation}</p>
          </div>
        ) : null}
      </Panel>

      <Panel title="Raw Evidence" subtitle="Explicit localhost request only" className="span-all">
        <InvestigatorEvidence
          call={call}
          contextRuntime={contextRuntime}
          onContextApiEnabledChange={onContextApiEnabledChange}
        />
      </Panel>
    </div>
  );
}

function InvestigatorEvidence({
  call,
  contextRuntime,
  onContextApiEnabledChange,
}: {
  call: CallRow;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
}) {
  const [options, setOptions] = useState(defaultContextOptions);
  const [contextState, setContextState] = useState<ContextLoadState>({ status: 'idle' });
  const canUseContextServer = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const canLoadContext = canUseContextServer && contextRuntime.contextApiEnabled;

  useEffect(() => {
    setContextState({ status: 'idle' });
  }, [call.id, options.includeToolOutput, options.includeCompactionHistory, options.maxChars, options.maxEntries, options.mode]);

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

  async function loadEvidence() {
    setContextState({ status: 'loading', message: 'Loading selected-turn evidence...' });
    try {
      const payload = await loadCallContext(call.id, contextRuntime, options);
      setContextState({ status: 'loaded', payload });
    } catch (error) {
      setContextState({ status: 'error', message: errorMessage(error) });
    }
  }

  function updateOption<K extends keyof ContextRequestOptions>(key: K, value: ContextRequestOptions[K]) {
    setOptions(current => ({ ...current, [key]: value }));
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
          Enable context loading
        </button>
        <button
          className="primary-button"
          type="button"
          onClick={loadEvidence}
          disabled={!canLoadContext || contextState.status === 'loading'}
        >
          Show turn evidence
        </button>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={options.includeToolOutput}
            disabled={!canLoadContext || contextState.status === 'loading'}
            onChange={event => updateOption('includeToolOutput', event.target.checked)}
          />
          Include tool output
        </label>
        <label className="toggle-row">
          <input
            type="checkbox"
            checked={options.maxChars === 0}
            disabled={!canLoadContext || contextState.status === 'loading'}
            onChange={event => updateOption('maxChars', event.target.checked ? 0 : defaultContextOptions.maxChars)}
          />
          No char limit
        </label>
      </div>
      {contextState.status === 'idle' && contextState.message ? <p className="context-state-note">{contextState.message}</p> : null}
      {contextState.status === 'loading' ? <p className="context-state-note">{contextState.message}</p> : null}
      {contextState.status === 'error' ? <p className="context-state-note error">{contextState.message}</p> : null}
      {contextState.status === 'loaded' ? <ContextEvidence payload={contextState.payload} /> : null}
      <p className="privacy-note">
        Raw context is read from the local JSONL source only after this explicit action and is not embedded in static dashboard HTML.
      </p>
    </div>
  );
}

function ContextEvidence({ payload }: { payload: CallContextPayload }) {
  const entries = payload.entries ?? [];
  const omitted = payload.omitted ?? {};

  return (
    <div className="context-evidence">
      <div className="context-evidence-summary">
        <InvestigatorMetric label="Entries" value={formatNumber(entries.length)} detail={String(payload.context_mode ?? 'quick')} />
        <InvestigatorMetric label="Visible chars" value={formatNumber(Number(payload.visible_char_count ?? 0))} detail="redacted local text" />
        <InvestigatorMetric label="Visible tokens" value={formatNumber(Number(payload.visible_token_estimate ?? 0))} detail="estimator" />
        <InvestigatorMetric label="Older omitted" value={formatNumber(Number(omitted.older_entries ?? 0))} detail="entry budget" />
      </div>
      <div className="context-entry-list">
        {entries.slice(0, 10).map((entry, index) => (
          <article className="context-entry" key={`${entry.type ?? 'entry'}-${entry.line_number ?? index}`}>
            <div className="context-entry-meta">
              <strong>{entry.label || entry.role || entry.type || `Entry ${index + 1}`}</strong>
              <span>{entry.line_number ? `line ${entry.line_number}` : entry.timestamp || 'local evidence'}</span>
            </div>
            <pre>{entry.text || '[no visible text]'}</pre>
          </article>
        ))}
        {!entries.length ? <p className="empty-state">No visible evidence entries returned for this call.</p> : null}
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
      <div className="composition-bar" aria-label="Token composition">
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

function contextRuntimeMessage(runtime: ContextRuntime): string {
  if (runtime.fileMode) {
    return 'Static file mode cannot read local JSONL context. Use serve-dashboard with the context API enabled.';
  }
  if (!runtime.apiToken) {
    return 'Context loading requires the localhost dashboard server API token.';
  }
  if (!runtime.contextApiEnabled) {
    return 'Context API is available but off. Enable it here before loading selected-turn evidence.';
  }
  return 'Context API is enabled. Load selected-turn evidence from the local JSONL source only when needed.';
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function cacheState(call: CallRow): string {
  if (call.cachedPct < 25) return 'cold or weak cache';
  if (call.cachedPct < 50) return 'partial cache reuse';
  return 'healthy cache reuse';
}
