import { afterEach, describe, expect, it, vi } from 'vitest';

import type { ContextRuntime } from './types';
import { loadAgenticInvestigation, loadInvestigationWalk } from './investigations';

const runtime: ContextRuntime = {
  apiToken: 'local-investigation-token',
  contextApiEnabled: true,
  fileMode: false,
};

afterEach(() => {
  vi.restoreAllMocks();
});

describe('investigation API', () => {
  it('loads the MCP-equivalent agentic report with scoped filters', async () => {
    const payload = {
      schema: 'codex-usage-tracker-agentic-investigation-v1',
      content_mode: 'aggregate_investigation',
      includes_indexed_content: false,
      includes_raw_fragments: false,
      privacy_mode: 'normal',
      goal: 'token_waste',
      filters: {},
      summary: { finding_count: 0, top_finding: null, confidence: 'low', source_reports: [] },
      findings: [],
      recommended_next_tools: [],
      caveats: [],
    };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(payload));

    await expect(loadAgenticInvestigation(runtime, { includeArchived: true, evidenceLimit: 7 })).resolves.toEqual(payload);

    const [input, init] = fetchMock.mock.calls[0];
    const url = new URL(String(input), 'http://localhost');
    expect(url.pathname).toBe('/api/investigations/agentic');
    expect(url.searchParams.get('goal')).toBe('token_waste');
    expect(url.searchParams.get('evidence_limit')).toBe('7');
    expect(url.searchParams.get('include_archived')).toBe('1');
    expect(new Headers(init?.headers).get('X-Codex-Usage-Token')).toBe(runtime.apiToken);
  });

  it('forwards cancellation to the agentic investigation request', async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}));

    await loadAgenticInvestigation(runtime, {
      signal: controller.signal,
    } as Parameters<typeof loadAgenticInvestigation>[1] & { signal: AbortSignal });

    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it('loads a bounded local investigation walk without raw-fragment flags', async () => {
    const payload = {
      schema: 'codex-usage-tracker-investigation-walk-v1',
      content_mode: 'local_content_index',
      includes_indexed_content: true,
      includes_raw_fragments: false,
      privacy_mode: 'normal',
      question: 'Why are files reopened?',
      filters: {},
      summary: { branch_count: 0, supported_branch_count: 0, top_hypothesis: null, confidence: 'low' },
      branches: [],
      recommended_next_tools: [],
    };
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse(payload));

    const result = await loadInvestigationWalk(runtime, 'Why are files reopened?', {
      evidenceLimit: 5,
      minOccurrences: 3,
    });

    expect(result.includes_raw_fragments).toBe(false);
    const url = new URL(String(fetchMock.mock.calls[0][0]), 'http://localhost');
    expect(url.pathname).toBe('/api/investigations/walk');
    expect(url.searchParams.get('question')).toBe('Why are files reopened?');
    expect(url.searchParams.get('min_occurrences')).toBe('3');
  });

  it('forwards cancellation to a local investigation walk', async () => {
    const controller = new AbortController();
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}));

    await loadInvestigationWalk(runtime, 'Where is waste concentrated?', {
      signal: controller.signal,
    } as Parameters<typeof loadInvestigationWalk>[2] & { signal: AbortSignal });

    expect(fetchMock.mock.calls[0][1]?.signal).toBe(controller.signal);
  });

  it('rejects file-mode access before issuing a request', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');

    await expect(loadAgenticInvestigation({ ...runtime, fileMode: true })).rejects.toThrow(
      'localhost dashboard server',
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

function jsonResponse(payload: unknown): Response {
  return {
    ok: true,
    json: async () => payload,
  } as Response;
}
