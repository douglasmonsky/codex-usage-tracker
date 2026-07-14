import { Copy, Search } from 'lucide-react';
import { useEffect, useMemo, useState, type ReactNode } from 'react';

import {
  diagnosticFactSourceDefinitions,
  type DiagnosticFactRow,
  type DiagnosticFactSourceKey,
} from '../../api/diagnostics';
import type { CallRow, ContextRuntime, DashboardModel, DiagnosticSection } from '../../api/types';
import { LineChart } from '../../charts/LineChart';
import { Panel } from '../../components/Panel';
import { StatusBadge } from '../../components/StatusBadge';
import { PageLoadProgress } from '../../design';
import { formatCompact, money, pct } from '../shared/format';
import {
  FactCallsPanel,
  factCallsResult,
  type DashboardRowLoadControls,
  type FactLoadState,
  type FactSourcePanelState,
  StructuredFactsPanel,
} from './DiagnosticFactsPanels';
import { DiagnosticSnapshotMatrix } from './DiagnosticSnapshotMatrix';
import { FACT_CALL_PAGE_SIZE, diagnosticFactKey } from './diagnosticFactCalls';
import { factFromCalls, numericFactField } from './diagnosticFallbackFacts';
import type { FactCallSortState, FactSortState } from './diagnosticFactSorting';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';
import {
  useDiagnosticFactCalls,
  useDiagnosticFactSources,
  type DiagnosticFactLimitMap,
  type DiagnosticFactSortStateMap,
} from './useDiagnosticFactEvidence';

const DEFAULT_FACT_SORT_STATE: FactSortState = { key: 'uncached', direction: 'desc' };

export function diagnosticsCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  const facts = fallbackDiagnosticFacts(model.calls);
  const selectedFact = diagnosticFactFromUrl(facts) ?? facts[0] ?? null;
  return selectedFact ? fallbackDiagnosticFactCalls(selectedFact, model.calls) : [];
}

export function DiagnosticsPage({
  model,
  contextRuntime,
  includeArchived,
  sourceKey,
  sourceRevision,
  rowLoadControls,
  onOpenInvestigator,
  onCopyCallLink,
  globalFilters,
}: {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  includeArchived: boolean;
  sourceKey?: string;
  sourceRevision: string;
  rowLoadControls: DashboardRowLoadControls;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  globalFilters?: ReactNode;
}) {
  const [factSourceKey, setFactSourceKey] = useState<DiagnosticFactSourceKey>(() => diagnosticFactSourceFromUrl());
  const [factSortStates, setFactSortStates] = useState<DiagnosticFactSortStateMap>({});
  const [factLimits, setFactLimits] = useState<DiagnosticFactLimitMap>({});
  const [selectedFactKey, setSelectedFactKey] = useState('');
  const [factCallSort, setFactCallSort] = useState<FactCallSortState>({ key: 'tokens', direction: 'desc' });
  const canUseLiveFacts = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const factEvidence = useDiagnosticFactSources({
    activeSourceKey: factSourceKey,
    canUseLive: canUseLiveFacts,
    contextRuntime,
    includeArchived,
    sourceKey,
    sourceRevision,
    limits: factLimits,
    sorts: factSortStates,
  });
  const factStates = factEvidence.states;
  const factState = factStates[factSourceKey] ?? staticFactState();
  const factSort = factSortStates[factSourceKey] ?? defaultFactSortState();
  const factSources = useMemo<FactSourcePanelState[]>(
    () =>
      diagnosticFactSourceDefinitions.map(source => ({
        key: source.key,
        label: source.label,
        title: source.title,
        state: factStates[source.key] ?? staticFactState(),
      })),
    [factStates],
  );
  const fallbackFacts = useMemo(() => fallbackDiagnosticFacts(model.calls), [model.calls]);
  const liveFacts = factState.status === 'loaded' ? factState.payload.rows ?? [] : [];
  const usingLiveFacts = liveFacts.length > 0;
  const facts = usingLiveFacts ? liveFacts : fallbackFacts;
  const selectedFact = facts.find(fact => diagnosticFactKey(fact) === selectedFactKey) ?? facts[0] ?? null;
  const factCallEvidence = useDiagnosticFactCalls({
    canUseLive: canUseLiveFacts,
    contextRuntime,
    includeArchived,
    sourceKey,
    sourceRevision,
    fact: selectedFact,
    factCallSort,
    pageSize: FACT_CALL_PAGE_SIZE,
    usingLiveFacts,
  });
  const factCallsState = factCallEvidence.state;
  const fallbackFactCalls = useMemo(
    () => (selectedFact ? fallbackDiagnosticFactCalls(selectedFact, model.calls) : []),
    [model.calls, selectedFact],
  );
  const liveFactCallsResult = factCallsResult(factCallsState);
  const selectedFactCalls = liveFactCallsResult && usingLiveFacts ? liveFactCallsResult.calls : fallbackFactCalls;
  const activeFactSource =
    diagnosticFactSourceDefinitions.find(source => source.key === factSourceKey) ?? diagnosticFactSourceDefinitions[0];
  const loadedFactCount = factState.status === 'loaded' ? (factState.payload.rows?.length ?? 0) : 0;
  const matchedFactCount = factState.status === 'loaded' ? Number(factState.payload.total_matched_rows ?? loadedFactCount) : loadedFactCount;
  const canLoadMoreFacts =
    usingLiveFacts && factState.status === 'loaded' && matchedFactCount > loadedFactCount;
  const factStatusNoun = activeFactSource.key === 'facts' ? 'facts' : activeFactSource.label.toLowerCase();
  const factStatusLabel =
    factState.status === 'loaded'
      ? `Live ${factStatusNoun}: ${factState.payload.total_matched_rows ?? facts.length}`
      : factState.status === 'error'
        ? 'Static fallback facts'
        : contextRuntime.apiToken
          ? factState.message
          : 'Static fallback facts';
  const loadingFactModules = factEvidence.modules.some(
    module => module.status === 'loading' || module.status === 'updating',
  );

  useEffect(() => {
    if (!facts.length) {
      setSelectedFactKey('');
      return;
    }
    const selectedFromUrl = diagnosticFactFromUrl(facts);
    if (selectedFromUrl) {
      const nextKey = diagnosticFactKey(selectedFromUrl);
      if (nextKey !== selectedFactKey) {
        setSelectedFactKey(nextKey);
      }
      return;
    }
    if (!facts.some(fact => diagnosticFactKey(fact) === selectedFactKey)) {
      setSelectedFactKey(diagnosticFactKey(facts[0]));
    }
  }, [facts, factSourceKey, selectedFactKey]);

  function loadMoreFacts() {
    if (!canUseLiveFacts || factState.status !== 'loaded' || factEvidence.sourceIsUpdating(factSourceKey)) return;
    const currentRows = factState.payload.rows ?? [];
    const totalMatched = Math.max(Number(factState.payload.total_matched_rows ?? currentRows.length), currentRows.length);
    const nextLimit = Math.min(Math.max(currentRows.length + activeFactSource.limit, activeFactSource.limit), totalMatched);
    if (nextLimit <= currentRows.length) return;
    setFactLimits(current => ({ ...current, [factSourceKey]: nextLimit }));
  }

  function selectFactSource(sourceKey: DiagnosticFactSourceKey) {
    setFactSourceKey(sourceKey);
    setSelectedFactKey('');
    syncDiagnosticFactUrl(sourceKey, null);
  }

  function selectFact(fact: DiagnosticFactRow) {
    setSelectedFactKey(diagnosticFactKey(fact));
    syncDiagnosticFactUrl(factSourceKey, fact);
  }

  return (
    <div className="diagnostics-layout">
      <div className="page-title-row span-all">
        <div>
          <h1>Diagnostics Notebook</h1>
          <p>Technical report system behavior usage patterns.</p>
        </div>
        <div className="toolbar">
          <StatusBadge label={factStatusLabel} tone={usingLiveFacts ? 'green' : 'blue'} />
          <StatusBadge label="Local Only" tone="green" />
        </div>
      </div>

      <PageLoadProgress
        active={canUseLiveFacts && loadingFactModules}
        completed={factEvidence.progress.ready}
        total={factEvidence.progress.total}
        label="Loading diagnostic fact sources"
        error={canUseLiveFacts ? factEvidence.progressError : null}
        modules={factEvidence.modules}
        updating={factEvidence.modules.some(module => module.status === 'updating')}
      />

      {globalFilters}

      <Panel title="Executive Findings" subtitle="Top observations aggregate telemetry" className="span-all">
        <div className="executive-grid">
          {model.diagnostics.slice(0, 3).map((section, index) => (
            <article className={`executive-card tone-${index + 1}`} key={section.title}>
              <span>{index + 1}</span>
              <strong>{section.title}</strong>
              <p>{section.finding}</p>
            </article>
          ))}
        </div>
      </Panel>

      <DiagnosticSnapshotMatrix
        model={model}
        contextRuntime={contextRuntime}
        includeArchived={includeArchived}
        sourceKey={sourceKey}
        sourceRevision={sourceRevision}
        onOpenInvestigator={onOpenInvestigator}
        onCopyCallLink={onCopyCallLink}
      />

      <div className="diagnostic-sections">
        {model.diagnostics.map(section => (
          <DiagnosticRow
            key={section.title}
            section={section}
            calls={relatedDiagnosticCalls(section, model.calls)}
            onOpenInvestigator={onOpenInvestigator}
            onCopyCallLink={onCopyCallLink}
          />
        ))}
      </div>

      <aside className="side-panel">
        <Panel title="Notebook Index" subtitle="Jump to section">
          <div className="index-list">
            {model.diagnostics.map((section, index) => (
              <span key={section.title}>
                <i>{index + 1}</i>
                {section.title}
                <StatusBadge label={section.status} tone={section.status === 'Ready' ? 'green' : 'orange'} />
              </span>
            ))}
          </div>
        </Panel>

        <StructuredFactsPanel
          sources={factSources}
          activeSourceKey={factSourceKey}
          facts={facts}
        selectedFact={selectedFact}
        factState={factState}
        factSort={factSort}
        onFactSortChange={sort => setFactSortStates(current => ({ ...current, [factSourceKey]: sort }))}
        onSelectSource={selectFactSource}
        onSelectFact={selectFact}
        canLoadMoreFacts={canLoadMoreFacts}
        loadingMoreFacts={factEvidence.sourceIsUpdating(factSourceKey)}
        onLoadMoreFacts={loadMoreFacts}
        onOpenInvestigator={onOpenInvestigator}
        onCopyCallLink={onCopyCallLink}
      />

        <FactCallsPanel
          selectedFact={selectedFact}
          calls={selectedFactCalls}
          status={factCallsState}
          usingLiveFacts={usingLiveFacts}
          liveResult={liveFactCallsResult}
          factCallSort={factCallSort}
          rowLoadControls={rowLoadControls}
          onFactCallSortChange={setFactCallSort}
          onLoadMore={factCallEvidence.loadMore}
          onOpenInvestigator={onOpenInvestigator}
          onCopyCallLink={onCopyCallLink}
        />
      </aside>
    </div>
  );
}

function DiagnosticRow({
  section,
  calls,
  onOpenInvestigator,
  onCopyCallLink,
}: {
  section: DiagnosticSection;
  calls: CallRow[];
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
}) {
  return (
    <Panel title={section.title} subtitle={section.metric}>
      <div className="diagnostic-row">
        <LineChart series={section.series} yLabel={section.title} height={180} />
        <div>
          <h3>Finding</h3>
          <p>{section.finding}</p>
          <StatusBadge label={`${section.confidence} confidence`} tone={section.confidence === 'High' ? 'green' : 'orange'} />
        </div>
        <div className="mini-evidence">
          <span>Evidence</span>
          <strong>{section.metric}</strong>
          <small>{section.status}</small>
        </div>
      </div>

      <div className="diagnostic-call-list">
        <div className="section-heading compact">
          <h3>Evidence Calls</h3>
          <span>{calls.length ? `${calls.length} aggregate rows` : 'No matching calls'}</span>
        </div>
        {calls.length ? (
          <ol className="thread-mini-timeline">
            {calls.map(call => (
              <li
                key={`${section.title}-${call.id}`}
                className="diagnostic-call-row has-row-action"
                tabIndex={0}
                aria-label={`Open investigator for diagnostic call ${call.thread} ${call.model}`}
                onClick={() => onOpenInvestigator(call.id)}
                onKeyDown={event => {
                  if (event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    onOpenInvestigator(call.id);
                  }
                }}
              >
                <span>{call.time}</span>
                <strong>{call.thread}</strong>
                <em>
                  {call.model} / {call.effort} - {formatCompact(call.totalTokens)} tokens - {pct(call.cachedPct)} cache -{' '}
                  {money(call.cost)}
                </em>
                <span className="table-action-group">
                  <button
                    className="table-action-button"
                    type="button"
                    aria-label={`Open investigator for diagnostic call ${call.thread} ${call.model}`}
 onKeyDown={stopRowActionKeyDown}
                    onClick={event => {
                      event.stopPropagation();
                      onOpenInvestigator(call.id);
                    }}
                  >
                    <Search size={14} /> Open
                  </button>
                  <button
                    className="table-action-button"
                    type="button"
                    aria-label={`Copy link for diagnostic call ${call.thread} ${call.model}`}
 onKeyDown={stopRowActionKeyDown}
                    onClick={event => {
                      event.stopPropagation();
                      onCopyCallLink(call.id);
                    }}
                  >
                    <Copy size={14} /> Copy
                  </button>
                </span>
              </li>
            ))}
          </ol>
        ) : (
          <p className="empty-state">No loaded aggregate call rows match diagnostic section.</p>
        )}
      </div>
    </Panel>
  );
}

function relatedDiagnosticCalls(section: DiagnosticSection, calls: CallRow[]): CallRow[] {
  const title = section.title.toLowerCase();
  const rows = [...calls];
  if (title.includes('cache')) {
    return rows
      .filter(call => call.signal === 'cache-risk' || call.cachedPct < 35 || call.uncachedInput > 50_000)
      .sort((left, right) => left.cachedPct - right.cachedPct || right.uncachedInput - left.uncachedInput)
      .slice(0, 3);
  }
  if (title.includes('thread')) {
    return rows.sort((left, right) => right.totalTokens - left.totalTokens || right.cost - left.cost).slice(0, 3);
  }
  if (title.includes('tool') || title.includes('command')) {
    return rows
      .filter(call => call.tags.some(tag => ['file-heavy', 'subagent', 'large'].includes(tag)))
      .sort((left, right) => right.input - left.input)
      .slice(0, 3);
  }
  if (title.includes('usage') || title.includes('drain')) {
    return rows.sort((left, right) => right.credits - left.credits || right.totalTokens - left.totalTokens).slice(0, 3);
  }
  return rows.sort((left, right) => right.totalTokens - left.totalTokens).slice(0, 3);
}

function fallbackDiagnosticFacts(calls: CallRow[]): DiagnosticFactRow[] {
  const specs = [
    {
      fact_type: 'cache',
      fact_name: 'large_uncached_input',
      calls: calls.filter(call => call.signal === 'cache-risk' || call.cachedPct < 35 || call.uncachedInput > 50_000),
    },
    {
      fact_type: 'model',
      fact_name: 'high_effort',
      calls: calls.filter(call => call.effort.toLowerCase() === 'high'),
    },
    {
      fact_type: 'tool',
      fact_name: 'file_heavy_or_subagent',
      calls: calls.filter(call => call.tags.some(tag => ['file-heavy', 'subagent', 'large'].includes(tag))),
    },
    {
      fact_type: 'usage',
      fact_name: 'high_credit_call',
      calls: [...calls].sort((left, right) => right.credits - left.credits).slice(0, 5),
    },
  ];

  return specs
    .filter(spec => spec.calls.length)
    .map(spec => factFromCalls(spec.fact_type, spec.fact_name, spec.calls))
    .sort(
      (left, right) =>
        numericFactField(right.associated_uncached_input_tokens) - numericFactField(left.associated_uncached_input_tokens) ||
        numericFactField(right.associated_total_tokens) - numericFactField(left.associated_total_tokens),
    );
}

function fallbackDiagnosticFactCalls(fact: DiagnosticFactRow, calls: CallRow[]): CallRow[] {
  const factName = String(fact.fact_name ?? '');
  const factLabel = `${fact.fact_type ?? ''} ${fact.fact_name ?? ''}`.toLowerCase();
  if (factName === 'large_uncached_input' || factLabel.includes('cache') || factLabel.includes('uncached')) {
    return calls
      .filter(call => call.signal === 'cache-risk' || call.cachedPct < 35 || call.uncachedInput > 50_000)
      .sort((left, right) => right.uncachedInput - left.uncachedInput)
      .slice(0, 5);
  }
  if (factName === 'high_effort' || factLabel.includes('effort') || factLabel.includes('model')) {
    return calls
      .filter(call => call.effort.toLowerCase() === 'high')
      .sort((left, right) => right.totalTokens - left.totalTokens)
      .slice(0, 5);
  }
  if (
    factName === 'file_heavy_or_subagent' ||
    factLabel.includes('tool') ||
    factLabel.includes('function') ||
    factLabel.includes('file') ||
    factLabel.includes('subagent') ||
    factLabel.includes('command')
  ) {
    const taggedCalls = calls.filter(call => call.tags.some(tag => ['file-heavy', 'subagent', 'large'].includes(tag)));
    return (taggedCalls.length ? taggedCalls : calls)
      .sort((left, right) => right.input - left.input)
      .slice(0, 5);
  }
  return [...calls].sort((left, right) => right.credits - left.credits || right.totalTokens - left.totalTokens).slice(0, 5);
}

function diagnosticFactSourceFromUrl(): DiagnosticFactSourceKey {
  const sourceKey = new URLSearchParams(window.location.search).get('diagnostic_source');
  const source = diagnosticFactSourceDefinitions.find(candidate => candidate.key === sourceKey);
  return source?.key ?? 'facts';
}

function diagnosticFactFromUrl(facts: DiagnosticFactRow[]): DiagnosticFactRow | null {
  const key = new URLSearchParams(window.location.search).get('diagnostic_fact')?.trim();
  if (!key) return null;
  const existing = facts.find(fact => diagnosticFactUrlKey(fact) === key || diagnosticFactKey(fact) === key);
  if (existing) return existing;
  const [factType, ...nameParts] = key.split(':');
  const factName = nameParts.join(':');
  return factType || factName ? { fact_type: factType, fact_name: factName || 'unknown' } : null;
}

function diagnosticFactUrlKey(fact: DiagnosticFactRow): string {
  return `${fact.fact_type ?? ''}:${fact.fact_name ?? ''}`;
}

function syncDiagnosticFactUrl(sourceKey: DiagnosticFactSourceKey, fact: DiagnosticFactRow | null) {
  const url = new URL(window.location.href);
  url.searchParams.set('view', 'diagnostics');
  if (sourceKey === 'facts') {
    url.searchParams.delete('diagnostic_source');
  } else {
    url.searchParams.set('diagnostic_source', sourceKey);
  }
  if (fact) {
    url.searchParams.set('diagnostic_fact', diagnosticFactUrlKey(fact));
  } else {
    url.searchParams.delete('diagnostic_fact');
  }
  window.history.replaceState(null, '', url);
}

function staticFactState(): FactLoadState {
  return { status: 'idle', message: 'Static aggregate fallback' };
}

function defaultFactSortState(): FactSortState {
  return DEFAULT_FACT_SORT_STATE;
}
