import { describe, expect, it } from 'vitest';

import { buildDashboardTarget, dashboardTargetPrompt } from './dashboardTargets';

describe('dashboard targets', () => {
  it.each(['normal', 'redacted', 'strict'] as const)('builds a deterministic %s target', privacy_mode => {
    const target = buildDashboardTarget({
      view: 'call', record_id: 'record-123', history: 'all', privacy_mode,
      service_origin: 'http://127.0.0.1:47821',
      filters: { mode: 'full', call_q: 'forbidden-fixture-value', api_token: 'forbidden-fixture-value' },
    });

    expect(target.relative_url).toBe('/react-dashboard.html?history=all&mode=full&record=record-123&view=call');
    expect(target.absolute_url).toBe(`http://127.0.0.1:47821${target.relative_url}`);
    expect(target.filters).toEqual({ mode: 'full' });
    expect(JSON.stringify(target)).not.toContain('forbidden-fixture-value');
    expect(dashboardTargetPrompt(target)).not.toContain('forbidden-fixture-value');
  });

  it('uses a relative target and fallback when no active origin is known', () => {
    const target = buildDashboardTarget({ view: 'overview' });
    expect(target.absolute_url).toBeNull();
    expect(target.fallback_instruction).toBe('codex-usage-tracker serve-dashboard --open');
    expect(dashboardTargetPrompt(target)).toContain(target.relative_url);
  });

  it('maps only canonical selectors for their cataloged destinations', () => {
    const sessionKey = 'session:019e374d-c19f-7da3-a44f-8de043a7a64e';
    expect(buildDashboardTarget({ view: 'threads', thread_key: sessionKey }).relative_url)
      .toBe('/react-dashboard.html?thread_key=session%3A019e374d-c19f-7da3-a44f-8de043a7a64e&view=threads');
    expect(buildDashboardTarget({ view: 'diagnostics', diagnostic_fact: 'activity:search_read_command' }).relative_url)
      .toBe('/react-dashboard.html?diagnostic_fact=activity%3Asearch_read_command&view=diagnostics');
    for (const diagnosticFact of ['skill:codex-usage-tracker', 'skill:brooks-test']) {
      expect(buildDashboardTarget({ view: 'diagnostics', diagnostic_fact: diagnosticFact }).diagnostic_fact)
        .toBe(diagnosticFact);
    }
    expect(buildDashboardTarget({ view: 'usage-drain', limit_evidence: 'stable' }).relative_url)
      .toBe('/react-dashboard.html?limit_hypothesis=stable&view=usage-drain');
    expect(buildDashboardTarget({ view: 'call', record_id: 'a'.repeat(64) }).record_id)
      .toBe('a'.repeat(64));
    expect(() => buildDashboardTarget({ view: 'overview', record_id: 'private' })).toThrow();
  });

  it('rejects non-loopback origins and uncataloged views', () => {
    expect(() => buildDashboardTarget({ view: 'overview', service_origin: 'https://example.com' })).toThrow(/loopback/);
    expect(() => buildDashboardTarget({ view: 'overview', service_origin: 'http://secret@localhost:47821' })).toThrow(/credentials/);
    expect(() => buildDashboardTarget({ view: 'secrets' })).toThrow(/dashboard view/);
  });

  it.each(['normal', 'redacted', 'strict'] as const)('rejects unsafe selectors in %s mode', privacy_mode => {
    const cases = [
      ['call', 'record_id'], ['threads', 'thread_key'],
      ['diagnostics', 'diagnostic_fact'], ['usage-drain', 'limit_evidence'],
    ] as const;
    const unsafeValues = [
      'forbidden-fixture-value', 'sk-' + 'abcdefghijklmnopqrstuvwxyz123456',
      '/Users/private/project', 'name with spaces', 'line\nbreak', 'folder\\name',
      'value?token=secret', 'value#fragment',
      '{"raw":"text"}', 'raw-context-fragment', 'indexed-prompt-fragment',
      'project:private-label', 'a'.repeat(130),
      'xox' + 'b-1234567890-abcdefghijklmnop', 'summarize-my-bank-account',
      'client-acme-production',
    ];
    cases.forEach(([view, selector]) => unsafeValues.forEach(value => {
      expect(() => buildDashboardTarget({ view, privacy_mode, [selector]: value })).toThrow();
    }));
  });

  it.each(['normal', 'redacted', 'strict'] as const)('drops invalid handoff filters in %s mode', privacy_mode => {
    const cases = [
      ['investigator', 'finding'], ['calls', 'explore'], ['calls', 'detail'],
      ['calls', 'source'], ['calls', 'sort'], ['calls', 'direction'],
      ['calls', 'density'], ['calls', 'page'], ['call', 'return'], ['call', 'mode'],
      ['threads', 'expand'], ['threads', 'risk'], ['threads', 'thread_call_sort'],
      ['threads', 'thread_call_page'], ['usage-drain', 'usage_plan'],
      ['usage-drain', 'usage_effort'], ['usage-drain', 'usage_subagents'],
      ['usage-drain', 'usage_sample'], ['usage-drain', 'usage_confidence'],
      ['usage-drain', 'limit_window'], ['diagnostics', 'diagnostic_source'],
      ['reports', 'report'],
    ];
    cases.forEach(([view, filterKey]) => {
      const target = buildDashboardTarget({
        view, privacy_mode, filters: { [filterKey]: 'forbidden-fixture-value' },
      });
      expect(target.filters).toEqual({});
      expect(JSON.stringify(target)).not.toContain('forbidden-fixture-value');
      expect(target.relative_url).not.toContain('forbidden-fixture-value');
      expect(target.absolute_url).toBeNull();
      expect(dashboardTargetPrompt(target)).not.toContain('forbidden-fixture-value');
    });
  });

  it('matches Python boolean and numeric query normalization', () => {
    const target = buildDashboardTarget({
      view: 'usage-drain',
      filters: { usage_subagents: false, usage_sample: 80, usage_confidence: 0.55 },
    });
    expect(target.relative_url).toBe(
      '/react-dashboard.html?usage_confidence=0.55&usage_sample=80&usage_subagents=false&view=usage-drain',
    );
  });

  it('applies the label-bearing identifier rule by privacy mode', () => {
    expect(buildDashboardTarget({
      view: 'threads', thread_key: 'thread:Project Alpha', privacy_mode: 'normal',
    }).thread_key).toBe('thread:Project Alpha');
    for (const privacy_mode of ['redacted', 'strict'] as const) {
      expect(() => buildDashboardTarget({
        view: 'threads', thread_key: 'thread:Project Alpha', privacy_mode,
      })).toThrow(/thread_key/);
    }
  });

  it.each(['normal', 'redacted', 'strict'] as const)('catalogs reports in %s mode', privacy_mode => {
    for (const value of [
      'xox' + 'b-1234567890-abcdefghijklmnop', 'summarize-my-bank-account', 'client-acme-production',
    ]) {
      const target = buildDashboardTarget({ view: 'reports', privacy_mode, filters: { report: value } });
      expect(target.filters).toEqual({});
      expect(JSON.stringify(target)).not.toContain(value);
      expect(dashboardTargetPrompt(target)).not.toContain(value);
    }
  });

  it('accepts only the verified report catalog', () => {
    for (const report of [
      'fast-mode-proxy', 'cost-curves', 'usage-remaining',
      'allowance-change', 'weekly-credits', 'usage-drain-model',
    ]) {
      expect(buildDashboardTarget({ view: 'reports', filters: { report } }).filters)
        .toEqual({ report });
    }
  });

  it.each(['normal', 'redacted', 'strict'] as const)('keeps session keys in %s mode', privacy_mode => {
    const thread_key = 'session:019e374d-c19f-7da3-a44f-8de043a7a64e';
    expect(buildDashboardTarget({ view: 'threads', thread_key, privacy_mode }).thread_key)
      .toBe(thread_key);
  });

  it.each([
    [0, '0'], [-0, '0'], [1, '1'], [0.55, '0.55'], [1e-7, '0.0000001'],
  ] as const)('canonically serializes numeric filter %s', (value, serialized) => {
    expect(buildDashboardTarget({
      view: 'usage-drain', filters: { usage_confidence: value },
    }).relative_url).toBe(
      `/react-dashboard.html?usage_confidence=${serialized}&view=usage-drain`,
    );
  });

  it.each([-0.01, 1.01, Number.POSITIVE_INFINITY, Number.NaN])('drops invalid number %s', value => {
    expect(buildDashboardTarget({
      view: 'usage-drain', filters: { usage_confidence: value },
    }).filters).toEqual({});
  });

  it.each(['http://localhost', 'http://localhost:80', 'http://localhost:65536'])(
    'requires a valid non-privileged service port for %s', origin => {
      expect(() => buildDashboardTarget({ view: 'overview', service_origin: origin })).toThrow();
    },
  );
});
