import { Copy, Search } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import {
  cachedDiagnosticFactCalls,
  cachedMergedDiagnosticFactCalls,
  cachedDiagnosticFactSource,
  diagnosticFactSourceDefinitions,
  loadDiagnosticFactCalls,
  loadDiagnosticFactSource,
  rememberMergedDiagnosticFactCalls,
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
  type FactCallsState,
  type FactLoadState,
  type FactSourcePanelState,
  StructuredFactsPanel,
} from './DiagnosticFactsPanels';
import { DiagnosticSnapshotMatrix } from './DiagnosticSnapshotMatrix';
import { FACT_CALL_PAGE_SIZE, diagnosticFactKey, factCallsHasMore, mergeFactCallResults } from './diagnosticFactCalls';
import type { FactCallSortState, FactSortState } from './diagnosticFactSorting';
import { stopRowActionKeyDown } from '../shared/rowActionEvents';

type FactSourceStateMap = Partial<Record<DiagnosticFactSourceKey, FactLoadState>>;
type FactSortStateMap = Partial<Record<DiagnosticFactSourceKey, FactSortState>>;
const DEFAULT_FACT_SORT_STATE: FactSortState = { key: 'uncached', direction: 'desc' };

export function diagnosticsCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  const facts = fallbackDiagnosticFacts(model.calls);
  const selectedFact = diagnosticFactFromUrl(facts) ?? facts[0] ?? null;
  return selectedFact ? fallbackDiagnosticFactCalls(selectedFact, model.calls) : [];
}

export function DiagnosticsPage({
  model,
  contextRuntime,
  rowLoadControls,
  onOpenInvestigator,
  onCopyCallLink,
  globalFilters,
}: {
  model: DashboardModel;
  contextRuntime: ContextRuntime;
  rowLoadControls: DashboardRowLoadControls;
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  globalFilters?: ReactNode;
}) {
  const [factSourceKey, setFactSourceKey] = useState<DiagnosticFactSourceKey>(() => diagnosticFactSourceFromUrl());
  const [factStates, setFactStates] = useState<FactSourceStateMap>(() => cachedFactStates(contextRuntime, {}));
  const [factSortStates, setFactSortStates] = useState<FactSortStateMap>({});
  const [selectedFactKey, setSelectedFactKey] = useState('');
  const [loadingMoreFactSourceKey, setLoadingMoreFactSourceKey] = useState<DiagnosticFactSourceKey | null>(null);
  const [factCallSort, setFactCallSort] = useState<FactCallSortState>({ key: 'tokens', direction: 'desc' });
  const [factCallsState, setFactCallsState] = useState<FactCallsState>({
    status: 'idle',
    message: 'Select a diagnostic fact',
  });
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
  const canUseLiveFacts = Boolean(contextRuntime.apiToken) && !contextRuntime.fileMode;
  const completedFactModules = diagnosticFactSourceDefinitions.filter(
    source => factStates[source.key]?.status === 'loaded',
  ).length;
  const loadingFactModules = diagnosticFactSourceDefinitions.some(
    source => factStates[source.key]?.status === 'loading',
  );
  const factProgressError = diagnosticFactSourceDefinitions
    .map(source => factStates[source.key])
    .find((state): state is Extract<FactLoadState, { status: 'error' }> => state?.status === 'error');

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

  useEffect(() => {
    if (!contextRuntime.apiToken || contextRuntime.fileMode) {
      setFactStates({});
      return;
    }

    let cancelled = false;
    const cachedStates = cachedFactStates(contextRuntime, factSortStates);
    if (allFactSourcesLoaded(cachedStates)) {
      setFactStates(cachedStates);
      return;
    }

    setFactStates({ ...loadingFactStateMap(), ...cachedStates });
    void Promise.all(
      diagnosticFactSourceDefinitions.map(async source => {
        const cachedState = cachedStates[source.key];
        if (cachedState?.status === 'loaded') {
          return [source.key, cachedState] as const;
        }
        try {
          const sourceSort = factSortStates[source.key] ?? defaultFactSortState();
          const payload = await loadDiagnosticFactSource(source.key, contextRuntime, {
            sort: sourceSort.key,
            direction: sourceSort.direction,
          });
          return [source.key, { status: 'loaded', payload } satisfies FactLoadState] as const;
        } catch (error) {
          return [source.key, { status: 'error', message: errorMessage(error) } satisfies FactLoadState] as const;
        }
      }),
    ).then(entries => {
      if (!cancelled) {
        setFactStates(Object.fromEntries(entries) as FactSourceStateMap);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [contextRuntime, factSortStates]);

  useEffect(() => {
    if (!selectedFact || !usingLiveFacts || !contextRuntime.apiToken || contextRuntime.fileMode) {
      setFactCallsState({ status: 'idle', message: 'Static aggregate fact calls' });
      return;
    }

    let cancelled = false;
    const cacheOptions = {
      limit: FACT_CALL_PAGE_SIZE,
      sort: factCallSort.key,
      direction: factCallSort.direction,
    };
    const cachedMergedResult = cachedMergedDiagnosticFactCalls(selectedFact, contextRuntime, cacheOptions);
    if (cachedMergedResult) {
      setFactCallsState({ status: 'loaded', result: cachedMergedResult });
      return;
    }
    const cachedResult = cachedDiagnosticFactCalls(selectedFact, contextRuntime, {
      limit: FACT_CALL_PAGE_SIZE,
      sort: factCallSort.key,
      direction: factCallSort.direction,
    });
    if (cachedResult) {
      rememberMergedDiagnosticFactCalls(selectedFact, contextRuntime, cachedResult, cacheOptions);
      setFactCallsState({ status: 'loaded', result: cachedResult });
      return;
    }

    setFactCallsState({ status: 'loading', message: 'Loading calls for selected fact...' });
    loadDiagnosticFactCalls(selectedFact, contextRuntime, cacheOptions)
      .then(result => {
        if (!cancelled) {
          rememberMergedDiagnosticFactCalls(selectedFact, contextRuntime, result, cacheOptions);
          setFactCallsState({ status: 'loaded', result });
        }
      })
      .catch(error => {
        if (!cancelled) {
          setFactCallsState({ status: 'error', message: errorMessage(error) });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [contextRuntime, factCallSort, selectedFact, usingLiveFacts]);

  async function loadMoreFactCalls() {
    if (!selectedFact || !usingLiveFacts || !contextRuntime.apiToken || contextRuntime.fileMode) return;
    const current = factCallsResult(factCallsState);
    if (!current || !factCallsHasMore(current) || factCallsState.status === 'appending') return;
    setFactCallsState({ status: 'appending', result: current });
    try {
      const next = await loadDiagnosticFactCalls(selectedFact, contextRuntime, {
        limit: FACT_CALL_PAGE_SIZE,
        offset: current.calls.length,
        sort: factCallSort.key,
        direction: factCallSort.direction,
      });
      const merged = mergeFactCallResults(current, next);
      rememberMergedDiagnosticFactCalls(selectedFact, contextRuntime, merged, {
        limit: FACT_CALL_PAGE_SIZE,
        sort: factCallSort.key,
        direction: factCallSort.direction,
      });
      setFactCallsState({ status: 'loaded', result: merged });
    } catch (error) {
      setFactCallsState({ status: 'error', message: errorMessage(error), result: current });
    }
  }

  async function loadMoreFacts() {
    if (!contextRuntime.apiToken || contextRuntime.fileMode || factState.status !== 'loaded' || loadingMoreFactSourceKey) return;
    const currentRows = factState.payload.rows ?? [];
    const totalMatched = Math.max(Number(factState.payload.total_matched_rows ?? currentRows.length), currentRows.length);
    const nextLimit = Math.min(Math.max(currentRows.length + activeFactSource.limit, activeFactSource.limit), totalMatched);
    if (nextLimit <= currentRows.length) return;
    setLoadingMoreFactSourceKey(factSourceKey);
    try {
      const payload = await loadDiagnosticFactSource(factSourceKey, contextRuntime, {
        limit: nextLimit,
        sort: factSort.key,
        direction: factSort.direction,
      });
      setFactStates(current => ({
        ...current,
        [factSourceKey]: { status: 'loaded', payload },
      }));
    } catch (error) {
      setFactStates(current => ({
        ...current,
        [factSourceKey]: { status: 'error', message: errorMessage(error) },
      }));
    } finally {
      setLoadingMoreFactSourceKey(null);
    }
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
        completed={completedFactModules}
        total={diagnosticFactSourceDefinitions.length}
        label="Loading diagnostic fact sources"
        error={canUseLiveFacts ? factProgressError?.message : null}
        updating={completedFactModules > 0}
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
        loadingMoreFacts={loadingMoreFactSourceKey === factSourceKey}
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
          onLoadMore={loadMoreFactCalls}
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
        numberField(right.associated_uncached_input_tokens) - numberField(left.associated_uncached_input_tokens) ||
        numberField(right.associated_total_tokens) - numberField(left.associated_total_tokens),
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

function factFromCalls(factType: string, factName: string, calls: CallRow[]): DiagnosticFactRow {
  const largest = [...calls].sort((left, right) => right.totalTokens - left.totalTokens)[0];
  const associatedInput = calls.reduce((sum, call) => sum + call.input, 0);
  const associatedCached = calls.reduce((sum, call) => sum + Math.round(call.input * (call.cachedPct / 100)), 0);
  return {
    fact_type: factType,
    fact_name: factName,
    fact_category: 'react-fallback',
    occurrences: calls.length,
    associated_calls: calls.length,
    associated_input_tokens: associatedInput,
    associated_cached_input_tokens: associatedCached,
    associated_uncached_input_tokens: calls.reduce((sum, call) => sum + call.uncachedInput, 0),
    associated_output_tokens: calls.reduce((sum, call) => sum + call.output, 0),
    associated_reasoning_output_tokens: calls.reduce((sum, call) => sum + call.reasoningOutput, 0),
    associated_total_tokens: calls.reduce((sum, call) => sum + call.totalTokens, 0),
    avg_cache_ratio: associatedInput ? associatedCached / associatedInput : 0,
    largest_call_tokens: largest?.totalTokens ?? 0,
    largest_record_id: largest?.id ?? null,
    latest_event_timestamp: largest?.rawTime || largest?.time || null,
    action_hint: 'Open associated aggregate calls in the full Call Investigator.',
  };
}

function numberField(value: unknown): number {
  const numeric = Number(value ?? 0);
  return Number.isFinite(numeric) ? numeric : 0;
}

function staticFactState(): FactLoadState {
  return { status: 'idle', message: 'Static aggregate fallback' };
}

function cachedFactStates(contextRuntime: ContextRuntime, factSortStates: FactSortStateMap): FactSourceStateMap {
  if (!contextRuntime.apiToken || contextRuntime.fileMode) return {};
  return Object.fromEntries(
    diagnosticFactSourceDefinitions.flatMap(source => {
      const sourceSort = factSortStates[source.key] ?? defaultFactSortState();
      const payload = cachedDiagnosticFactSource(source.key, contextRuntime, {
        sort: sourceSort.key,
        direction: sourceSort.direction,
      });
      return payload ? [[source.key, { status: 'loaded', payload } satisfies FactLoadState] as const] : [];
    }),
  ) as FactSourceStateMap;
}

function allFactSourcesLoaded(factStates: FactSourceStateMap): boolean {
  return diagnosticFactSourceDefinitions.every(source => factStates[source.key]?.status === 'loaded');
}

function defaultFactSortState(): FactSortState {
  return DEFAULT_FACT_SORT_STATE;
}

function loadingFactStateMap(): FactSourceStateMap {
  return Object.fromEntries(
    diagnosticFactSourceDefinitions.map(source => [
      source.key,
      { status: 'loading', message: `Loading ${source.title.toLowerCase()}...` } satisfies FactLoadState,
    ]),
  ) as FactSourceStateMap;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
