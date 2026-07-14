import { describe, expect, it } from 'vitest';

import type { DiagnosticFactRow } from '../api/diagnostics';
import {
  diagnosticFactCallsQueryOptions,
  diagnosticFactSourceQueryOptions,
  diagnosticSnapshotQueryOptions,
  type DiagnosticQueryRequest,
} from './diagnosticsQueries';

const request: DiagnosticQueryRequest = {
  runtime: {
    apiToken: 'private-diagnostics-token',
    contextApiEnabled: true,
    fileMode: false,
  },
  includeArchived: false,
  sourceKey: 'fixture-source',
  sourceRevision: 'revision-1',
};

const fact: DiagnosticFactRow = {
  fact_type: 'cache',
  fact_name: 'large_uncached_input',
};

describe('diagnostics query options', () => {
  it('keys fact sources by credential-free source, scope, sort, and pagination', () => {
    const key = diagnosticFactSourceQueryOptions({
      ...request,
      factSourceKey: 'facts',
      limit: 50,
      sort: 'uncached',
      direction: 'desc',
    }).queryKey;

    expect(JSON.stringify(key)).not.toContain('private-diagnostics-token');
    expect(diagnosticFactSourceQueryOptions({
      ...request,
      factSourceKey: 'facts',
      limit: 50,
      sort: 'uncached',
      direction: 'desc',
    }).queryKey).toEqual(key);
    expect(diagnosticFactSourceQueryOptions({
      ...request,
      sourceRevision: 'revision-2',
      factSourceKey: 'facts',
    }).queryKey).not.toEqual(key);
    expect(diagnosticFactSourceQueryOptions({
      ...request,
      includeArchived: true,
      factSourceKey: 'facts',
    }).queryKey).not.toEqual(key);
    expect(diagnosticFactSourceQueryOptions({
      ...request,
      factSourceKey: 'tools',
    }).queryKey).not.toEqual(key);
    expect(diagnosticFactSourceQueryOptions({
      ...request,
      factSourceKey: 'facts',
      limit: 100,
    }).queryKey).not.toEqual(key);
  });

  it('keys fact-call pages by fact identity and scan controls', () => {
    const key = diagnosticFactCallsQueryOptions({
      ...request,
      fact,
      pageSize: 8,
      sort: 'tokens',
      direction: 'desc',
    }).queryKey;

    expect(JSON.stringify(key)).not.toContain('private-diagnostics-token');
    expect(diagnosticFactCallsQueryOptions({
      ...request,
      fact: { ...fact },
      pageSize: 8,
      sort: 'tokens',
      direction: 'desc',
    }).queryKey).toEqual(key);
    expect(diagnosticFactCallsQueryOptions({
      ...request,
      fact: { ...fact, fact_name: 'cold_resume' },
    }).queryKey).not.toEqual(key);
    expect(diagnosticFactCallsQueryOptions({
      ...request,
      fact,
      sort: 'cache',
    }).queryKey).not.toEqual(key);
  });

  it('shares snapshot identity across dashboard consumers', () => {
    const overviewKey = diagnosticSnapshotQueryOptions({
      ...request,
      snapshotKey: 'overview',
    }).queryKey;
    const commandsKey = diagnosticSnapshotQueryOptions({
      ...request,
      snapshotKey: 'commands',
    }).queryKey;

    expect(overviewKey).not.toEqual(commandsKey);
    expect(JSON.stringify(overviewKey)).not.toContain('private-diagnostics-token');
    expect(diagnosticSnapshotQueryOptions({
      ...request,
      sourceRevision: 'revision-2',
      snapshotKey: 'overview',
    }).queryKey).not.toEqual(overviewKey);
  });
});
