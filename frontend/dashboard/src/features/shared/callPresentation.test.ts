import { describe, expect, it } from 'vitest';
import { cacheState, contextWindowLabel, sourceLine, summarizeTopCounts } from './callPresentation';

describe('call presentation helpers', () => {
  it('labels cache state thresholds consistently across call surfaces', () => {
    expect(cacheState({ cachedPct: 12 })).toBe('cold or weak cache');
    expect(cacheState({ cachedPct: 25 })).toBe('partial cache reuse');
    expect(cacheState({ cachedPct: 49.9 })).toBe('partial cache reuse');
    expect(cacheState({ cachedPct: 50 })).toBe('healthy cache reuse');
  });

  it('formats source-line labels with unavailable fallback', () => {
    expect(sourceLine({ sourceFile: 'thread.jsonl', lineNumber: 42 })).toBe('thread.jsonl:42');
    expect(sourceLine({ sourceFile: 'thread.jsonl' })).toBe('thread.jsonl');
    expect(sourceLine({ sourceFile: '' })).toBe('Not available');
  });

  it('formats context-window labels with model window detail', () => {
    expect(contextWindowLabel({ contextWindowPct: null })).toBe('Not reported');
    expect(contextWindowLabel({ contextWindowPct: 63.25, modelContextWindow: 128_000 })).toBe('63.3% of 128K');
    expect(contextWindowLabel({ contextWindowPct: 12 })).toBe('12.0%');
  });

  it('summarizes top counts in Calls and Call Investigator formats', () => {
    expect(summarizeTopCounts(['o4-mini', 'o4-mini', 'o3'], { style: 'x', emptyLabel: 'no model mix' })).toBe(
      'o4-mini x2, o3 x1',
    );
    expect(summarizeTopCounts(['', 'o3', '', 'codex-1'], { limit: 3 })).toBe(
      'Unknown (2), codex-1 (1), o3 (1)',
    );
    expect(summarizeTopCounts([], { emptyLabel: 'no model mix' })).toBe('no model mix');
  });
});
