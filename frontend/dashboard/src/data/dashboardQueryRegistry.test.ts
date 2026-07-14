import { describe, expect, it } from 'vitest';

import {
  exploreCallsSchema,
  exploreThreadCallsSchema,
  exploreThreadsSchema,
} from './contracts/explore';
import {
  overviewRecommendationsSchema,
  overviewSummarySchema,
} from './contracts/overview';
import {
  dashboardModuleProgress,
  dashboardQueryDefinition,
  dashboardQueryDefinitions,
  dashboardQueryKey,
  dashboardQueryPolicies,
  dashboardQuerySource,
  deriveDashboardModuleState,
} from './dashboardQueryRegistry';

describe('dashboard query registry', () => {
  it('builds stable keys from non-secret source, scope, and module inputs', () => {
    const callsQuery = dashboardQueryDefinition('calls');
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

    expect(dashboardQueryKey(callsQuery, source, scope, 'tokens', 'desc')).toEqual(
      dashboardQueryKey(callsQuery, source, { ...scope }, 'tokens', 'desc'),
    );
    expect(dashboardQueryKey(callsQuery, source, scope)).not.toEqual(
      dashboardQueryKey(callsQuery, { ...source, sourceRevision: 'revision-8' }, scope),
    );
    expect(dashboardQueryKey(callsQuery, source, scope)).not.toEqual(
      dashboardQueryKey(callsQuery, source, { ...scope, historyScope: 'active' }),
    );
    expect(JSON.stringify(dashboardQueryKey(callsQuery, source, scope))).not.toContain('token');
  });

  it('keeps registered query identities and representative keys collision-free', () => {
    const ids = dashboardQueryDefinitions.map(definition => definition.id);
    const endpoints = dashboardQueryDefinitions.map(definition => definition.endpoint);
    const source = dashboardQuerySource({ sourceKey: 'fixture-db', sourceRevision: 'revision-1' });
    const keys = dashboardQueryDefinitions.map(definition => JSON.stringify(
      dashboardQueryKey(definition, source, { historyScope: 'all', loadWindow: 'all' }),
    ));

    expect(new Set(ids).size).toBe(ids.length);
    expect(new Set(endpoints).size).toBe(endpoints.length);
    expect(new Set(keys).size).toBe(keys.length);
    expect(dashboardQueryDefinitions.every(definition => definition.endpoint.startsWith('/api/')))
      .toBe(true);
  });

  it('matches the response schemas enforced by focused dashboard decoders', () => {
    const schemas = Object.fromEntries(
      dashboardQueryDefinitions.map(definition => [definition.id, definition.schema]),
    );

    expect(schemas).toMatchObject({
      'overview-summary': overviewSummarySchema,
      'overview-recommendations': overviewRecommendationsSchema,
      calls: exploreCallsSchema,
      threads: exploreThreadsSchema,
      'thread-calls': exploreThreadCallsSchema,
    });
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
