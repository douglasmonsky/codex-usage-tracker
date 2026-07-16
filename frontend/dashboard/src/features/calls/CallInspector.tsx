import {
  Activity,
  BarChart3,
  Copy,
  Database,
  GitBranch,
  LockKeyhole,
  Search,
  ShieldCheck,
  type LucideIcon,
} from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import type { CallRow, ContextRuntime } from '../../api/types';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { threadCallContextQueryOptions } from '../../data/exploreQueries';
import { CallCacheDelta } from '../shared/CallCacheDelta';
import { CallDecisionCard } from '../shared/CallDecisionCard';
import { CallSourceMetadata } from '../shared/CallSourceMetadata';
import { TokenPricingBreakdown } from '../shared/TokenPricingBreakdown';
import { ThreadCallTimeline } from '../shared/ThreadCallTimeline';
import { billingBasisDetail, cacheState, summarizeTopCounts } from '../shared/callPresentation';
import { copyText } from '../shared/copyText';
import { formatCompact, formatNumber, money, pct } from '../shared/format';
import { CallSignalPucks } from '../shared/tables';
import { compareCallTimeDescending } from './callsFilterSort';
import { CallContextEvidence } from './CallContextEvidence';
import { DetailRow, DrillMetric } from './CallDetailPrimitives';
import { serviceTierDetail } from './serviceTier';

type DrillDownTab = 'summary' | 'tokens' | 'cache' | 'thread' | 'evidence';

const drillDownTabs: Array<{ id: DrillDownTab; label: string; icon: LucideIcon }> = [
  { id: 'summary', label: 'Summary', icon: Activity },
  { id: 'tokens', label: 'Tokens', icon: BarChart3 },
  { id: 'cache', label: 'Cache', icon: Database },
  { id: 'thread', label: 'Thread', icon: GitBranch },
  { id: 'evidence', label: 'Evidence', icon: LockKeyhole },
];

export function CallInspector({
  call,
  calls,
  contextRuntime,
  includeArchived,
  sourceRevision,
  hydrateThreadCalls,
  onContextApiEnabledChange,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  call: CallRow | null;
  calls: CallRow[];
  contextRuntime: ContextRuntime;
  includeArchived: boolean;
  sourceRevision: string;
  hydrateThreadCalls: boolean;
  onContextApiEnabledChange: (enabled: boolean) => void;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const [activeTab, setActiveTab] = useState<DrillDownTab>('summary');
  const [copyStatus, setCopyStatus] = useState('');
  const localThreadCalls = useMemo(() => {
    if (!call) return [];
    return calls.filter(candidate => candidate.thread === call.thread).sort(compareCallTimeDescending);
  }, [call, calls]);
  const threadCallsQuery = useQuery({
    ...threadCallContextQueryOptions({
      runtime: contextRuntime,
      includeArchived,
      sourceRevision,
      threadKey: call?.threadKey || call?.thread || '',
      selectedRecordId: call?.id ?? '',
      selectedEventTimestamp: call?.eventTimestamp ?? '',
    }),
    enabled: hydrateThreadCalls && !contextRuntime.fileMode && Boolean(contextRuntime.apiToken) && Boolean(call),
    placeholderData: previous => previous,
  });
  const threadCalls = useMemo(() => {
    const loaded = threadCallsQuery.data?.rows ?? localThreadCalls;
    if (!call || loaded.some(candidate => candidate.id === call.id)) return loaded;
    return [...loaded, call].sort(compareCallTimeDescending);
  }, [call, localThreadCalls, threadCallsQuery.data]);

  if (!call) {
    return (
      <aside className="side-panel drilldown-panel">
        <Panel title="Call Drill-Down" subtitle="No matching call">
          <p className="empty-state">No aggregate row matches the active filters.</p>
        </Panel>
      </aside>
    );
  }

  return (
    <aside className="side-panel drilldown-panel">
      <Panel title="Call Drill-Down" subtitle={`${call.thread} / ${call.model}`}>
        <div className="call-summary">
          <StatusBadge label="Aggregate only" tone="green" />
          <CallSignalPucks call={call} />
          <StatusBadge label="Raw context gated" tone="blue" />
          <span className="call-id">{call.id.slice(0, 12)}</span>
        </div>
        <div className="action-row">
<button className="toolbar-button" type="button" onClick={() => onOpenInvestigator(call.id)}>
<Search size={16} />
Open investigator
</button>
<button className="toolbar-button" type="button" onClick={() => copyInvestigatorLink(call, setCopyStatus)}>
<Copy size={16} />
Copy link
</button>
</div>
{copyStatus ? <p className="context-state-note">{copyStatus}</p> : null}
<div className="drilldown-tabs" role="tablist" aria-label="Call drill-down sections">
          {drillDownTabs.map(tab => {
            const Icon = tab.icon;
            const selected = activeTab === tab.id;
            return (
              <button
                type="button"
                role="tab"
                aria-selected={selected}
                className={selected ? 'active' : ''}
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
              >
                <Icon size={14} />
                {tab.label}
              </button>
            );
          })}
        </div>
        <div className="drilldown-tab-panel" role="tabpanel">
          {activeTab === 'summary' ? <SummaryTab call={call} /> : null}
          {activeTab === 'tokens' ? <TokensTab call={call} /> : null}
          {activeTab === 'cache' ? <CacheTab call={call} calls={threadCalls} /> : null}
          {activeTab === 'thread' ? (
            <ThreadTab
              call={call}
              calls={threadCalls}
              onOpenInvestigator={onOpenInvestigator}
              onCopyCallLink={onCopyCallLink}
            />
          ) : null}
          {activeTab === 'evidence' ? (
            <CallContextEvidence
              key={call.id}
              call={call}
              contextRuntime={contextRuntime}
              onContextApiEnabledChange={onContextApiEnabledChange}
            />
          ) : null}
        </div>
      </Panel>
    </aside>
  );
}

function SummaryTab({ call }: { call: CallRow }) {
  return (
    <>
    <div className="drilldown-metric-grid">
      <DrillMetric label="Total tokens" value={formatNumber(call.totalTokens)} detail={`${formatCompact(call.input)} input`} />
      <DrillMetric label="Uncached input" value={formatNumber(call.uncachedInput)} detail="fresh billed input" />
        <DrillMetric label="Cache hit rate" value={pct(call.cachedPct)} detail={cacheState(call)} />
        <DrillMetric label="Estimated cost" value={money(call.cost)} detail={billingBasisDetail(call)} />
        <DrillMetric label="Duration" value={call.duration} detail={serviceTierDetail(call)} />
<DrillMetric label="Usage credits" value={call.credits ? call.credits.toFixed(3) : '-'} detail={call.usageCreditConfidence} />
    </div>
    <CallDecisionCard call={call} />
    <CallSourceMetadata call={call} />
    <CallAccountingSnapshot call={call} />
    <TokenComposition call={call} />
    <CacheMiniChart call={call} />
      {call.recommendation ? (
        <div className="recommendation-box">
          <ShieldCheck size={16} />
          <p>{call.recommendation}</p>
        </div>
      ) : null}
    </>
  );
}

function CallAccountingSnapshot({ call }: { call: CallRow }) {
  return (
    <div className="composition-card accounting-snapshot-card">
      <div className="composition-head">
        <strong>Accounting Snapshot</strong>
        <span>pricing, credits, and cache savings</span>
      </div>
      <TokenPricingBreakdown call={call} />
    </div>
  );
}

function TokensTab({ call }: { call: CallRow }) {
  return (
    <>
<TokenComposition call={call} />
<TokenPricingBreakdown call={call} />
</>
);
}

function CacheTab({ call, calls }: { call: CallRow; calls: CallRow[] }) {
  return (
    <>
      <CacheMiniChart call={call} />
      <CallCacheDelta call={call} calls={calls} />
      <dl className="detail-list">
<DetailRow label="Cache state" value={cacheState(call)} />
<DetailRow label="Cache hit rate" value={pct(call.cachedPct)} />
<DetailRow label="Fresh share" value={pct(Math.max(100 - call.cachedPct, 0))} />
<DetailRow label="Signal" value={call.signal} />
</dl>
<p className="privacy-note">Use this readout to decide whether the aggregate call needs deeper raw-context investigation.</p>
</>
);
}

function ThreadTab({
  call,
  calls,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  call: CallRow;
  calls: CallRow[];
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  const totalTokens = calls.reduce((sum, row) => sum + row.totalTokens, 0);
  const totalCost = calls.reduce((sum, row) => sum + row.cost, 0);
  const averageCache = calls.reduce((sum, row) => sum + row.cachedPct, 0) / Math.max(calls.length, 1);
  const selectedIndex = Math.max(calls.findIndex(row => row.id === call.id), 0);
  const timelineCount = Math.min(Math.max(calls.length, 1), 5);
  const source = call.sourceFile ? `${call.sourceFile}${call.lineNumber ? `:${call.lineNumber}` : ''}` : 'Not available';

  return (
    <>
      <div className="drilldown-metric-grid">
        <DrillMetric label="Loaded thread calls" value={formatNumber(calls.length)} detail={`selected ${selectedIndex + 1} of ${calls.length}`} />
        <DrillMetric label="Thread tokens" value={formatCompact(totalTokens)} detail="loaded aggregate rows" />
        <DrillMetric label="Thread cost" value={money(totalCost)} detail="estimated aggregate" />
          <DrillMetric
            label="Avg cache"
            value={pct(averageCache)}
            detail={summarizeTopCounts(calls.map(row => row.model), { style: 'x', emptyLabel: 'no model mix' })}
          />
        <DrillMetric label="Context window" value={call.contextWindowPct === null ? '-' : pct(call.contextWindowPct)} detail={call.modelContextWindow ? `${formatCompact(call.modelContextWindow)} window` : 'not reported'} />
        <DrillMetric label="Parent thread" value={call.parentThread || '-'} detail={call.parentSessionId || 'no parent session'} />
      </div>
      <div className="composition-card">
        <div className="composition-head">
          <strong>Thread timeline</strong>
          <span>{timelineCount} nearby loaded calls</span>
        </div>
        <ThreadCallTimeline
          selectedCall={call}
          calls={calls}
          onOpenInvestigator={onOpenInvestigator}
          onCopyCallLink={onCopyCallLink}
          copyAriaContext="side-panel thread call"
        />
      </div>
<div className="composition-card">
<div className="composition-head">
<strong>Call Narrative</strong>
<span>{call.initiatorConfidence || 'aggregate inference'}</span>
</div>
<dl className="detail-list compact">
<DetailRow label="Initiated by" value={call.initiator || 'unknown'} />
<DetailRow label="Initiator reason" value={call.initiatorReason || 'Not reported'} />
<DetailRow label="Parent thread" value={call.parentThread || 'None'} />
<DetailRow label="Parent session" value={call.parentSessionId || 'None'} />
<DetailRow label="Timestamp" value={call.time} />
<DetailRow label="Duration" value={call.duration} />
<DetailRow label="Previous gap" value={call.previousCallGap} />
</dl>
</div>
<dl className="detail-list">
<DetailRow label="Project" value={call.project || 'Unknown'} />
        <DetailRow label="Project path" value={call.projectRelativeCwd || call.cwd || '.'} />
        <DetailRow label="Source line" value={source} />
        <DetailRow label="Session" value={call.sessionId || 'Not available'} />
        <DetailRow label="Git branch" value={call.gitBranch || 'Unknown'} />
        <DetailRow label="Remote" value={call.gitRemoteLabel || call.gitRemoteHash || 'None'} />
      </dl>
    </>
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
  const total = Math.max(
    segments.reduce((sum, segment) => sum + segment.value, 0),
    1,
  );

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

function CacheMiniChart({ call }: { call: CallRow }) {
  const bars = [
    { label: 'Cache', value: Math.min(Math.max(call.cachedPct, 0), 100), color: '#2563eb' },
    { label: 'Fresh', value: Math.min(Math.max(100 - call.cachedPct, 0), 100), color: '#f59e0b' },
    { label: 'Output', value: Math.min(Math.max(call.output / Math.max(call.totalTokens, 1) * 100, 0), 100), color: '#059669' },
  ];

  return (
    <div className="cache-mini-card">
      <div>
        <strong>Cache delta readout</strong>
        <span>{cacheState(call)}</span>
      </div>
      <div className="cache-bars" aria-label="Cache delta readout">
        {bars.map(bar => (
          <span key={bar.label}>
            <i style={{ height: `${Math.max(bar.value, 4)}%`, background: bar.color }} />
            <em>{bar.label}</em>
          </span>
        ))}
      </div>
    </div>
  );
}

async function copyInvestigatorLink(call: CallRow, setCopyStatus: (status: string) => void) {
  try {
const url = new URL(window.location.href);
url.searchParams.set('view', 'call');
url.searchParams.set('record', call.id);
url.searchParams.set('return', 'calls');
const copied = await copyText(url.toString());
if (!copied) {
throw new Error('Clipboard unavailable');
}
setCopyStatus('Copied investigator link');
} catch {
    setCopyStatus('Copy unavailable in this browser');
  }
}
