import { afterEach, describe, expect, it } from 'vitest';
import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import {
  cacheContextCallsForCurrentUrl,
  diagnosticsCallsForCurrentUrl,
  investigatorCallsForCurrentUrl,
  reportCallsForCurrentUrl,
} from './legacyExportRows';

describe('legacy workbench compatibility exports', () => {
  afterEach(() => {
    window.history.replaceState(null, '', '/');
  });

  it('exports the selected cache thread without loading its retired page', () => {
    window.history.replaceState(
      null,
      '',
      '/?view=cache-context&cache_thread=thread-9f3a',
    );

    expect(cacheContextCallsForCurrentUrl(fixtureModel)).toHaveLength(1);
  });

  it('exports the selected diagnostic fact without loading its retired page', () => {
    window.history.replaceState(
      null,
      '',
      '/?view=diagnostics&diagnostic_fact=model:high_effort',
    );

    expect(diagnosticsCallsForCurrentUrl(fixtureModel)).toHaveLength(4);
  });

  it('exports the selected report evidence without loading its retired page', () => {
    window.history.replaceState(
      null,
      '',
      '/?view=reports&report=fast-mode-proxy',
    );

    expect(reportCallsForCurrentUrl(fixtureModel)).toHaveLength(4);
  });

  it('exports the selected investigation finding without loading its retired page', () => {
    window.history.replaceState(
      null,
      '',
      '/?view=investigator&finding=2',
    );

    expect(investigatorCallsForCurrentUrl(fixtureModel)).toHaveLength(6);
  });
});
