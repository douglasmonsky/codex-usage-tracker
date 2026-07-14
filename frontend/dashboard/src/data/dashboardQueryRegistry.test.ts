import { describe, expect, it } from 'vitest';

import {
  dashboardModuleProgress,
  dashboardQueryKey,
  dashboardQueryPolicies,
  dashboardQuerySource,
  deriveDashboardModuleState,
} from './dashboardQueryRegistry';

describe('dashboard query registry', () => {
  it('builds stable keys from non-secret source, scope, and module inputs', () => {
    const source = dashboardQuerySource({
      sourceKey: 'fixture-db',
      sourceRevision: 'revision-7',
    });
    const scope = {
      historyScope: 'all' as const,
      loadWindow: 'week' as const,
      limit: null,
      since: '2026-07-06T00:00:00Z',
    };

    expect(dashboardQueryKey('calls', source, scope, 'tokens', 'desc')).toEqual(
      dashboardQueryKey('calls', source, { ...scope }, 'tokens', 'desc'),
    );
    expect(dashboardQueryKey('calls', source, scope)).not.toEqual(
      dashboardQueryKey('calls', { ...source, sourceRevision: 'revision-8' }, scope),
    );
    expect(dashboardQueryKey('calls', source, scope)).not.toEqual(
      dashboardQueryKey('calls', source, { ...scope, historyScope: 'active' }),
    );
    expect(JSON.stringify(dashboardQueryKey('calls', source, scope))).not.toContain('token');
  });

  it('defines query lifecycle and browser persistence by data class', () => {
    expect(dashboardQueryPolicies.aggregate).toMatchObject({
      cancellation: 'observer',
      gcTime: 15 * 60_000,
      persistedCache: 'aggregate-only',
      retry: 1,
      staleTime: 30_000,
    });
    expect(dashboardQueryPolicies.detail.persistedCache).toBe('none');
    expect(dashboardQueryPolicies.heavyJob.cancellation).toBe('shared-job');
    expect(dashboardQueryPolicies.userAction.retry).toBe(0);
  });

  it('keeps completed modules ready while they refresh in the background', () => {
    expect(deriveDashboardModuleState({
      enabled: true,
      hasData: true,
      isError: false,
      isFetching: true,
      isPending: false,
    })).toBe('updating');
    expect(deriveDashboardModuleState({
      enabled: true,
      hasData: true,
      isError: true,
      isFetching: false,
      isPending: false,
    })).toBe('ready');
  });

  it('summarizes segmented progress without resetting ready siblings', () => {
    expect(dashboardModuleProgress(['ready', 'loading', 'updating', 'error'])).toEqual({
      ready: 2,
      total: 4,
      percent: 50,
      loading: 1,
      errors: 1,
    });
  });
});
