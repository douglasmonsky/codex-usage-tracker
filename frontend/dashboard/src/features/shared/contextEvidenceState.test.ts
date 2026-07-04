import { describe, expect, it } from 'vitest';
import type { CallContextPayload, ContextRuntime } from '../../api/types';
import {
  applyContextOptionsToUrl,
  contextErrorMessage,
  contextEvidenceNotes,
  contextOptionsFromSearch,
  contextRuntimeMessage,
  defaultContextOptions,
  olderContextOptions,
} from './contextEvidenceState';

function runtime(overrides: Partial<ContextRuntime> = {}): ContextRuntime {
  return {
    apiToken: 'token',
    contextApiEnabled: true,
    fileMode: false,
    ...overrides,
  };
}

function payload(overrides: Partial<CallContextPayload> = {}): CallContextPayload {
  return {
    record_id: 'record-1',
    include_tool_output: false,
    omitted: {},
    source: {},
    ...overrides,
  };
}

describe('contextEvidenceState', () => {
  it('pins default quick context options shared by side-panel and full-page evidence', () => {
  expect(defaultContextOptions).toEqual({
    includeToolOutput: false,
    includeCompactionHistory: false,
    maxChars: 8_000,
    maxEntries: 20,
    mode: 'quick',
  });
});

it('hydrates legacy call investigator context options from copied URL params', () => {
  expect(
    contextOptionsFromSearch(
      '?mode=full&max_entries=75&max_chars=0&include_tool_output=1&include_compaction_history=true',
    ),
  ).toEqual({
    includeToolOutput: true,
    includeCompactionHistory: true,
    maxChars: 0,
    maxEntries: 75,
    mode: 'full',
  });

  expect(
    contextOptionsFromSearch('?mode=bad&max_entries=-1&max_chars=oops&include_tool_output=nope', {
      includeToolOutput: true,
      includeCompactionHistory: true,
      maxChars: 400,
      maxEntries: 5,
      mode: 'quick',
    }),
  ).toEqual({
    includeToolOutput: true,
    includeCompactionHistory: true,
    maxChars: 400,
    maxEntries: 5,
    mode: 'quick',
  });
});

it('serializes non-default context options into copied call URLs', () => {
  const url = new URL(
    'https://example.test/react-dashboard.html?view=call&record=fixture-call-0&mode=quick&max_entries=20&max_chars=8000&include_tool_output=0&include_compaction_history=0',
  );

  applyContextOptionsToUrl(url, {
    includeToolOutput: true,
    includeCompactionHistory: true,
    maxChars: 0,
    maxEntries: 50,
    mode: 'full',
  });

  expect(url.searchParams.get('mode')).toBe('full');
  expect(url.searchParams.get('max_entries')).toBe('50');
  expect(url.searchParams.get('max_chars')).toBe('0');
  expect(url.searchParams.get('include_tool_output')).toBe('1');
  expect(url.searchParams.get('include_compaction_history')).toBe('1');

  applyContextOptionsToUrl(url, defaultContextOptions);

  for (const name of ['mode', 'max_entries', 'max_chars', 'include_tool_output', 'include_compaction_history']) {
    expect(url.searchParams.get(name)).toBeNull();
  }
});

it('explains context runtime gates in legacy dashboard language', () => {
    expect(contextRuntimeMessage(runtime({ fileMode: true }))).toBe(
      'Static file mode cannot read local JSONL context. Use serve-dashboard with the context API enabled.',
    );
    expect(contextRuntimeMessage(runtime({ apiToken: '' }))).toBe(
      'Context loading requires the localhost dashboard server API token.',
    );
    expect(contextRuntimeMessage(runtime({ contextApiEnabled: false }))).toBe(
      'Context API is available but off. Enable it here before loading selected-turn evidence.',
    );
    expect(contextRuntimeMessage(runtime())).toBe(
      'Context API is enabled. Load selected-turn evidence from the local JSONL source only when needed.',
    );
  });

  it('formats unknown context errors without throwing', () => {
    expect(contextErrorMessage(new Error('No context'))).toBe('No context');
    expect(contextErrorMessage('string failure')).toBe('string failure');
  });

  it('increments older-context entry depth while preserving no-cap requests', () => {
    expect(olderContextOptions(payload({ omitted: { max_entries: 20 } }), defaultContextOptions)).toMatchObject({
      maxEntries: 40,
      mode: 'quick',
    });
    expect(olderContextOptions(payload(), { ...defaultContextOptions, maxEntries: 50 })).toMatchObject({
      maxEntries: 100,
    });
    expect(olderContextOptions(payload({ omitted: { max_entries: 0 } }), { ...defaultContextOptions, maxEntries: 0 })).toMatchObject({
      maxEntries: 0,
    });
  });

  it('summarizes local evidence source, redaction, omitted entries, and no-cap state', () => {
    expect(
      contextEvidenceNotes(
        payload({
          include_tool_output: true,
          omitted: { older_entries: 30, over_budget_chars: 1234, max_chars: 0 },
          source: { file: 'thread.jsonl', line_number: 42 },
        }),
      ),
    ).toEqual([
      'Local JSONL context loaded on demand.',
      'Tool output included with redaction and size limits.',
      'Source: thread.jsonl:42.',
      '30 older entries omitted.',
      '1,234 chars over budget omitted.',
      'No character limit applied.',
    ]);
    expect(contextEvidenceNotes(payload())).toEqual([
      'Local JSONL context loaded on demand.',
      'Tool output hidden for this view.',
    ]);
  });
});
