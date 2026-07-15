import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  loadAllowanceAnalysis,
  loadAllowanceAnalysisJob,
  loadAllowanceEvidence,
  loadAllowanceSeries,
  loadAllowanceStatus,
  startAllowanceAnalysis,
} from './allowanceIntelligence';

const runtime = {
  apiToken: 'local-v2-token',
  contextApiEnabled: false,
  fileMode: false,
};

afterEach(() => vi.restoreAllMocks());

describe('allowance intelligence v2 transport', () => {
  it('loads no-store status with compact revision polling parameters', async () => {
    const payload = { schema: 'codex-usage-tracker-allowance-status-v2', revision: 'r2', changed: false };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(payload));

    await expect(loadAllowanceStatus(runtime, {
      includeArchived: true,
      sinceRevision: 'r1',
    })).resolves.toEqual(payload);

    const [input, init] = fetchMock.mock.calls[0];
    const url = new URL(String(input), 'http://localhost');
    expect(url.pathname).toBe('/api/allowance/status');
    expect(url.searchParams.get('include_archived')).toBe('1');
    expect(url.searchParams.get('since_revision')).toBe('r1');
    expect(url.searchParams.has('limit')).toBe(false);
    expect(init?.cache).toBe('no-store');
    expect(new Headers(init?.headers).get('X-Codex-Usage-Token')).toBe(runtime.apiToken);
  });

  it('uses finite series defaults and encodes a bounded custom range', async () => {
    const payload = { schema: 'codex-usage-tracker-allowance-series-v2', points: [], cycles: [] };
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(payload))
      .mockResolvedValueOnce(jsonResponse(payload));

    await loadAllowanceSeries(runtime);
    await loadAllowanceSeries(runtime, {
      rangePreset: 'custom',
      startAt: '2026-07-01T00:00:00Z',
      endAt: '2026-07-15T00:00:00Z',
      granularity: 'day',
      cohortId: 'codex',
    });

    const defaultUrl = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost');
    const customUrl = new URL(String(fetchMock.mock.calls[1][0]), 'http://localhost');
    expect(defaultUrl.searchParams.get('range_preset')).toBe('7d');
    expect(defaultUrl.searchParams.get('granularity')).toBe('auto');
    expect(defaultUrl.searchParams.get('window_kind')).toBe('weekly');
    expect(defaultUrl.searchParams.has('limit')).toBe(false);
    expect(customUrl.searchParams.get('range_preset')).toBe('custom');
    expect(customUrl.searchParams.get('start_at')).toBe('2026-07-01T00:00:00Z');
    expect(customUrl.searchParams.get('end_at')).toBe('2026-07-15T00:00:00Z');
    expect(customUrl.searchParams.get('granularity')).toBe('day');
  });

  it('uses latest-first finite evidence pages and revision-bound cursors', async () => {
    const payload = { schema: 'codex-usage-tracker-allowance-evidence-v2', rows: [], next_cursor: null };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(payload));

    await loadAllowanceEvidence(runtime, { before: 'cursor-r2', privacyMode: 'local' });

    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost');
    expect(url.pathname).toBe('/api/allowance/evidence');
    expect(url.searchParams.get('limit')).toBe('50');
    expect(url.searchParams.get('order')).toBe('desc');
    expect(url.searchParams.get('before')).toBe('cursor-r2');
    expect(url.searchParams.get('privacy_mode')).toBe('local');
    expect(url.searchParams.get('limit')).not.toBe('0');
  });

  it('reads persisted analysis, starts POST work, and polls one job', async () => {
    const missing = { schema: 'codex-usage-tracker-allowance-analysis-v2', status: 'missing' };
    const job = { schema: 'codex-usage-tracker-analysis-job-v1', job_id: 'analysis-1', status: 'running' };
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(jsonResponse(missing))
      .mockResolvedValueOnce(jsonResponse(job, 202))
      .mockResolvedValueOnce(jsonResponse(job));

    await loadAllowanceAnalysis(runtime, { forecastHorizon: 2 });
    await startAllowanceAnalysis(runtime, { forecastHorizon: 2 });
    await loadAllowanceAnalysisJob(runtime, 'analysis-1');

    const readUrl = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost');
    const startUrl = new URL(String(fetchMock.mock.calls[1][0]), 'http://localhost');
    const pollUrl = new URL(String(fetchMock.mock.calls[2][0]), 'http://localhost');
    expect(readUrl.pathname).toBe('/api/allowance/analysis');
    expect(readUrl.searchParams.get('forecast_horizon')).toBe('2');
    expect(startUrl.pathname).toBe('/api/allowance/analysis/jobs');
    expect(fetchMock.mock.calls[1][1]?.method).toBe('POST');
    expect(pollUrl.searchParams.get('job_id')).toBe('analysis-1');
  });

  it('rejects unbounded or invalid interactive options before fetch', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');

    await expect(loadAllowanceEvidence(runtime, { limit: 0 })).rejects.toThrow('between 1 and 500');
    await expect(loadAllowanceSeries(runtime, { rangePreset: 'custom' })).rejects.toThrow(
      'startAt and endAt',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

function jsonResponse(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response;
}
