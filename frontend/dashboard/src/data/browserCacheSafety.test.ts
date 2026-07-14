import { describe, expect, it } from 'vitest';

import { isBrowserCacheSafe } from './browserCacheSafety';

describe('browser cache safety', () => {
  it('accepts aggregate-only usage evidence', () => {
    expect(isBrowserCacheSafe({
      rows: [{ record_id: 'call-1', total_tokens: 42 }],
      raw_context_included: false,
      includes_raw_fragments: false,
    })).toBe(true);
  });

  it.each([
    { nested: { raw_context: 'private prompt' } },
    { nested: { raw_output: 'private output' } },
    { nested: { command_text: 'cat ~/.ssh/id_rsa' } },
    { nested: { content_fragments: ['private fragment'] } },
    { nested: { indexed_content: 'private index entry' } },
    { nested: { raw_content_included: true } },
    { nested: { excerpt: 'private excerpt', includes_raw_fragment: true } },
    { nested: { snippet: 'private snippet', includes_raw_fragment: true } },
    { nested: { includes_raw_fragments: true } },
  ])('rejects raw or indexed content: %j', payload => {
    expect(isBrowserCacheSafe(payload)).toBe(false);
  });

  it('rejects the real selected-call context response shape', () => {
    expect(isBrowserCacheSafe({
      schema: 'codex-usage-tracker-context-v1',
      source: { file: '/synthetic/private-input.log', line: 42 },
      entries: [{ kind: 'user', text: 'private prompt text' }],
    })).toBe(false);
  });
});
