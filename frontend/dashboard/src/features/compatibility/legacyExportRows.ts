import type {
  CallRow,
  DashboardModel,
  ThreadRow,
} from '../../api/types';
import type { DiagnosticFactRow } from '../../api/diagnostics';
import {
  factFromCalls,
  numericFactField,
} from '../diagnostics/diagnosticFallbackFacts';
import {
  callsForFinding,
} from '../investigator/investigationModel';
import {
  reportEvidenceCalls,
  reportFromUrl,
} from '../reports/reportModel';

export function cacheContextCallsForCurrentUrl(
  model: DashboardModel,
): CallRow[] {
  const selectedThread =
    cacheThreadFromUrl(model.threads) ?? model.threads[0] ?? null;
  if (!selectedThread) return [];

  return model.calls
    .filter(call => threadLabelsMatch(call.thread, selectedThread.name))
    .sort(compareCallTimeDescending);
}

export function diagnosticsCallsForCurrentUrl(
  model: DashboardModel,
): CallRow[] {
  const facts = fallbackDiagnosticFacts(model.calls);
  const selectedFact = diagnosticFactFromUrl(facts) ?? facts[0] ?? null;
  return selectedFact
    ? fallbackDiagnosticFactCalls(selectedFact, model.calls)
    : [];
}

export function reportCallsForCurrentUrl(model: DashboardModel): CallRow[] {
  return reportEvidenceCalls(
    reportFromUrl(model.reports) ?? model.reports[0],
    model.calls,
  );
}

export function investigatorCallsForCurrentUrl(
  model: DashboardModel,
): CallRow[] {
  const rank = Number(
    new URLSearchParams(window.location.search).get('finding') ?? '',
  );
  const finding =
    model.findings.find(candidate => candidate.rank === rank)
    ?? model.findings[0];
  return finding
    ? callsForFinding(finding, model.calls)
    : [...model.calls]
        .sort((left, right) => right.totalTokens - left.totalTokens)
        .slice(0, 8);
}

function cacheThreadFromUrl(threads: ThreadRow[]): ThreadRow | null {
  const threadName =
    new URLSearchParams(window.location.search).get('cache_thread')?.trim()
    || null;
  if (!threadName) return null;
  return threads.find(thread => thread.name === threadName) ?? null;
}

function compareCallTimeDescending(left: CallRow, right: CallRow): number {
  return (
    Date.parse(right.rawTime || right.time)
    - Date.parse(left.rawTime || left.time)
  );
}

function threadLabelsMatch(callThread: string, threadName: string): boolean {
  const callLabel = callThread.trim();
  const summaryLabel = threadName.trim();
  return callLabel.startsWith(summaryLabel) || summaryLabel.startsWith(callLabel);
}

function fallbackDiagnosticFacts(calls: CallRow[]): DiagnosticFactRow[] {
  const specs = [
    {
      factType: 'cache',
      factName: 'large_uncached_input',
      calls: calls.filter(
        call =>
          call.signal === 'cache-risk'
          || call.cachedPct < 35
          || call.uncachedInput > 50_000,
      ),
    },
    {
      factType: 'model',
      factName: 'high_effort',
      calls: calls.filter(call => call.effort.toLowerCase() === 'high'),
    },
    {
      factType: 'tool',
      factName: 'file_heavy_or_subagent',
      calls: calls.filter(call =>
        call.tags.some(tag => ['file-heavy', 'subagent', 'large'].includes(tag)),
      ),
    },
    {
      factType: 'usage',
      factName: 'high_credit_call',
      calls: [...calls]
        .sort((left, right) => right.credits - left.credits)
        .slice(0, 5),
    },
  ];

  return specs
    .filter(spec => spec.calls.length)
    .map(spec => factFromCalls(spec.factType, spec.factName, spec.calls))
    .sort(
      (left, right) =>
        numericFactField(right.associated_uncached_input_tokens)
          - numericFactField(left.associated_uncached_input_tokens)
        || numericFactField(right.associated_total_tokens)
          - numericFactField(left.associated_total_tokens),
    );
}

function fallbackDiagnosticFactCalls(
  fact: DiagnosticFactRow,
  calls: CallRow[],
): CallRow[] {
  const factName = String(fact.fact_name ?? '');
  const factLabel =
    `${fact.fact_type ?? ''} ${fact.fact_name ?? ''}`.toLowerCase();

  if (
    factName === 'large_uncached_input'
    || factLabel.includes('cache')
    || factLabel.includes('uncached')
  ) {
    return calls
      .filter(
        call =>
          call.signal === 'cache-risk'
          || call.cachedPct < 35
          || call.uncachedInput > 50_000,
      )
      .sort((left, right) => right.uncachedInput - left.uncachedInput)
      .slice(0, 5);
  }
  if (
    factName === 'high_effort'
    || factLabel.includes('effort')
    || factLabel.includes('model')
  ) {
    return calls
      .filter(call => call.effort.toLowerCase() === 'high')
      .sort((left, right) => right.totalTokens - left.totalTokens)
      .slice(0, 5);
  }
  if (
    factLabel.includes('tool')
    || factLabel.includes('function')
    || factLabel.includes('file')
    || factLabel.includes('subagent')
    || factLabel.includes('command')
  ) {
    const taggedCalls = calls.filter(call =>
      call.tags.some(tag => ['file-heavy', 'subagent', 'large'].includes(tag)),
    );
    return (taggedCalls.length ? taggedCalls : calls)
      .sort((left, right) => right.input - left.input)
      .slice(0, 5);
  }
  return [...calls]
    .sort(
      (left, right) =>
        right.credits - left.credits
        || right.totalTokens - left.totalTokens,
    )
    .slice(0, 5);
}

function diagnosticFactFromUrl(
  facts: DiagnosticFactRow[],
): DiagnosticFactRow | null {
  const key =
    new URLSearchParams(window.location.search)
      .get('diagnostic_fact')
      ?.trim()
    ?? '';
  if (!key) return null;
  return (
    facts.find(fact => `${fact.fact_type ?? ''}:${fact.fact_name ?? ''}` === key)
    ?? null
  );
}
