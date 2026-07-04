import type { CallRow } from '../../api/types';

export type ConfidenceFilter =
  | 'all'
  | 'cost-exact'
  | 'cost-estimated'
  | 'cost-unpriced'
  | 'credit-exact'
  | 'credit-estimated'
  | 'credit-override'
  | 'credit-missing';
export type TimeFilter = 'all' | 'today' | 'this-week' | 'last-7-days' | 'this-month' | 'custom';
export type SourceFilter = 'all' | 'project' | 'session' | 'git' | 'source-file' | 'missing';
export type CallsSortKey =
  | 'time'
  | 'duration'
  | 'gap'
  | 'attention'
  | 'thread'
  | 'initiator'
  | 'model'
  | 'effort'
  | 'total'
  | 'cached'
  | 'uncached'
  | 'output'
  | 'reasoning'
  | 'cost'
  | 'usage'
  | 'cache'
  | 'context';
export type SortDirection = 'asc' | 'desc';
export type CallsDateRange = { active: boolean; invalid: boolean; start: Date | null; endExclusive: Date | null; label: string };
export type SourceCoverage = { project: number; session: number; git: number; sourceFile: number; missing: number; total: number };

export type CallsFilterSummaryInput = {
  shownCount: number;
  totalCount: number;
  localQuery: string;
  globalQuery: string;
  modelFilter: string;
  effortFilter: string;
  confidenceFilter: ConfidenceFilter;
  sourceFilter: SourceFilter;
  timeFilter: TimeFilter;
  dateRangeStatus: CallsDateRange;
  activePresetLabel: string;
};

export function buildCallsFilterSummary(input: CallsFilterSummaryInput): string {
  const parts: string[] = [];
  const searchTerms = [input.localQuery.trim(), input.globalQuery.trim()].filter(Boolean);

  if (searchTerms.length) {
    parts.push(`Search ${searchTerms.map(term => `"${term}"`).join(' + ')}`);
  }
  if (input.modelFilter !== 'all') {
    parts.push(`Model ${input.modelFilter}`);
  }
  if (input.effortFilter !== 'all') {
    parts.push(`Effort ${input.effortFilter}`);
  }
  if (input.confidenceFilter !== 'all') {
    parts.push(`Confidence ${confidenceFilterLabel(input.confidenceFilter)}`);
  }
  if (input.sourceFilter !== 'all') {
    parts.push(`Source ${sourceFilterLabel(input.sourceFilter)}`);
  }
  if (input.dateRangeStatus.invalid) {
    parts.push('Date range invalid');
  } else if (input.dateRangeStatus.active || input.timeFilter !== 'all') {
    parts.push(input.dateRangeStatus.label || timeFilterLabel(input.timeFilter));
  }
  if (input.activePresetLabel) {
    parts.push(`Preset ${input.activePresetLabel}`);
  }

  const base = `Showing ${input.shownCount.toLocaleString()} of ${input.totalCount.toLocaleString()} aggregate rows`;
  return parts.length ? `${base} - Filters: ${parts.join('; ')}` : base;
}

export function sourceCoverageLabel(coverage: SourceCoverage, filter: SourceFilter): string {
  if (filter === 'project') return `${coverage.project.toLocaleString()} project/cwd rows`;
  if (filter === 'session') return `${coverage.session.toLocaleString()} session-linked rows`;
  if (filter === 'git') return `${coverage.git.toLocaleString()} git rows`;
  if (filter === 'source-file') return `${coverage.sourceFile.toLocaleString()} source-file rows`;
  if (filter === 'missing') return `${coverage.missing.toLocaleString()} rows missing source`;
  return `${coverage.project.toLocaleString()} project, ${coverage.session.toLocaleString()} session, ${coverage.git.toLocaleString()} git`;
}

export function callMatchesSourceFilter(call: CallRow, filter: SourceFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'project') return hasProjectSource(call);
  if (filter === 'session') return hasSessionSource(call);
  if (filter === 'git') return hasGitSource(call);
  if (filter === 'source-file') return hasSourceFile(call);
  return !hasAnySourceMetadata(call);
}

export function callMatchesConfidenceFilter(call: CallRow, filter: ConfidenceFilter): boolean {
  if (filter === 'all') {
    return true;
  }
  if (filter === 'cost-exact') {
    return !call.pricingEstimated && Number.isFinite(call.cost) && call.cost > 0;
  }
  if (filter === 'cost-estimated') {
    return call.pricingEstimated;
  }
  if (filter === 'cost-unpriced') {
    return !call.pricingEstimated && (!Number.isFinite(call.cost) || call.cost <= 0);
  }
  const confidence = call.usageCreditConfidence.toLowerCase();
  if (filter === 'credit-exact') {
    return confidence.includes('exact');
  }
  if (filter === 'credit-override') {
    return confidence.includes('override');
  }
  if (filter === 'credit-estimated') {
    return confidence.includes('estimated');
  }
  return confidence.includes('missing') || confidence.includes('unpriced');
}

export function summarizeSourceCoverage(calls: CallRow[]): SourceCoverage {
  return calls.reduce<SourceCoverage>(
    (summary, call) => ({
      project: summary.project + (hasProjectSource(call) ? 1 : 0),
      session: summary.session + (hasSessionSource(call) ? 1 : 0),
      git: summary.git + (hasGitSource(call) ? 1 : 0),
      sourceFile: summary.sourceFile + (hasSourceFile(call) ? 1 : 0),
      missing: summary.missing + (hasAnySourceMetadata(call) ? 0 : 1),
      total: summary.total + 1,
    }),
    { project: 0, session: 0, git: 0, sourceFile: 0, missing: 0, total: 0 },
  );
}

function hasProjectSource(call: CallRow): boolean {
  return Boolean(call.project || call.projectRelativeCwd || call.cwd || call.projectTags.length);
}

function hasSessionSource(call: CallRow): boolean {
  return Boolean(call.sessionId || call.turnId || call.parentSessionId);
}

function hasGitSource(call: CallRow): boolean {
  return Boolean(call.gitBranch || call.gitRemoteLabel || call.gitRemoteHash);
}

function hasSourceFile(call: CallRow): boolean {
  return Boolean(call.sourceFile || call.lineNumber !== null);
}

function hasAnySourceMetadata(call: CallRow): boolean {
  return hasProjectSource(call) || hasSessionSource(call) || hasGitSource(call) || hasSourceFile(call);
}

function confidenceFilterLabel(filter: ConfidenceFilter): string {
  if (filter === 'cost-exact') return 'exact cost';
  if (filter === 'cost-estimated') return 'estimated cost';
  if (filter === 'cost-unpriced') return 'unpriced cost';
  if (filter === 'credit-exact') return 'exact credit rate';
  if (filter === 'credit-estimated') return 'estimated credit mapping';
  if (filter === 'credit-override') return 'user credit override';
  return 'missing credit rate';
}

function sourceFilterLabel(filter: SourceFilter): string {
  if (filter === 'project') return 'project/cwd';
  if (filter === 'session') return 'session-linked';
  if (filter === 'git') return 'git metadata';
  if (filter === 'source-file') return 'source file';
  return 'missing source';
}

function timeFilterLabel(filter: TimeFilter): string {
  if (filter === 'today') return 'Today';
  if (filter === 'this-week') return 'This week';
  if (filter === 'last-7-days') return 'Last 7 days';
  if (filter === 'this-month') return 'This month';
  if (filter === 'custom') return 'Custom date range';
  return 'All time';
}
