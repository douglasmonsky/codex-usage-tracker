import { queryOptions } from '@tanstack/react-query';

import type { DiagnosticSnapshotKey } from '../api/diagnostics';
import {
  loadAgenticInvestigation,
  loadInvestigationWalk,
} from '../api/investigations';
import type { ContextRuntime } from '../api/types';
import {
  dashboardQueryKey,
  dashboardQueryOptions,
  dashboardQuerySource,
} from './dashboardQueryRegistry';
import { diagnosticSnapshotQueryOptions } from './diagnosticsQueries';

type InvestigatorQueryRequest = {
  runtime: ContextRuntime;
  includeArchived: boolean;
  sourceKey?: string;
  sourceRevision: string;
};

export type InvestigatorAgenticQueryRequest = InvestigatorQueryRequest & {
  evidenceLimit?: number;
  goal?: string;
};

export type InvestigatorSnapshotQueryRequest = InvestigatorQueryRequest & {
  snapshotKey: DiagnosticSnapshotKey;
};

export type InvestigatorWalkQueryRequest = InvestigatorQueryRequest & {
  evidenceLimit?: number;
  minOccurrences?: number;
  question: string;
};

export function investigatorAgenticQueryOptions(request: InvestigatorAgenticQueryRequest) {
  const evidenceLimit = Math.max(1, request.evidenceLimit ?? 8);
  const goal = request.goal?.trim() || 'token_waste';
  return queryOptions({
    queryKey: dashboardQueryKey(
      'investigator-agentic',
      investigatorQuerySource(request),
      investigatorQueryScope(request),
      goal,
      evidenceLimit,
    ),
    queryFn: ({ signal }) => loadAgenticInvestigation(request.runtime, {
      evidenceLimit,
      goal,
      includeArchived: request.includeArchived,
      signal,
    }),
    ...dashboardQueryOptions('aggregate'),
  });
}

export function investigatorSnapshotQueryOptions(request: InvestigatorSnapshotQueryRequest) {
  return diagnosticSnapshotQueryOptions(request);
}

export function investigatorWalkQueryOptions(request: InvestigatorWalkQueryRequest) {
  const evidenceLimit = Math.max(1, request.evidenceLimit ?? 6);
  const minOccurrences = Math.max(1, request.minOccurrences ?? 2);
  const question = normalizedQuestion(request.question);
  return queryOptions({
    queryKey: dashboardQueryKey(
      'investigator-walk',
      investigatorQuerySource(request),
      investigatorQueryScope(request),
      question,
      evidenceLimit,
      minOccurrences,
    ),
    queryFn: ({ signal }) => loadInvestigationWalk(request.runtime, question, {
      evidenceLimit,
      includeArchived: request.includeArchived,
      minOccurrences,
      signal,
    }),
    ...dashboardQueryOptions('userAction'),
  });
}

function investigatorQuerySource(request: InvestigatorQueryRequest) {
  return dashboardQuerySource({
    sourceKey: request.sourceKey ?? (request.runtime.fileMode ? 'static-file' : 'local-api'),
    sourceRevision: request.sourceRevision,
  });
}

function investigatorQueryScope(request: InvestigatorQueryRequest) {
  return {
    historyScope: request.includeArchived ? 'all' as const : 'active' as const,
  };
}

function normalizedQuestion(question: string): string {
  return question.trim() || 'Where is avoidable token waste concentrated?';
}
