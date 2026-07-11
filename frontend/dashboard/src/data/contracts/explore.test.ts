import { describe, expect, it } from 'vitest';

import { decodeExploreCalls, decodeExploreThreads, ExploreContractError } from './explore';

describe('Explore endpoint contracts', () => {
  it('decodes paged calls into dashboard rows', () => {
    const result = decodeExploreCalls({
      schema: 'codex-usage-tracker-calls-v1',
      rows: [{ record_id: 'call-1', event_timestamp: '2026-07-10T12:00:00Z', thread_name: 'Thread A', total_tokens: 42 }],
      row_count: 1,
      total_matched_rows: 3,
      limit: 1,
      offset: 1,
      has_more: true,
      next_offset: 2,
      raw_context_included: false,
    });

    expect(result.rows[0]).toMatchObject({ id: 'call-1', thread: 'Thread A', totalTokens: 42 });
    expect(result).toMatchObject({ rowCount: 1, totalMatchedRows: 3, hasMore: true, nextOffset: 2 });
  });

  it('derives compatibility paging metadata for older thread payloads', () => {
    const result = decodeExploreThreads({
      schema: 'codex-usage-tracker-threads-v1',
      rows: [{ thread_key: 'thread-a', thread_label: 'Thread A', latest_record_id: 'call-3', call_count: 3, total_tokens: 900 }],
      row_count: 1,
      limit: 1,
      offset: 0,
      include_archived: false,
      raw_context_included: false,
    });

    expect(result.rows[0]).toMatchObject({ threadKey: 'thread-a', threadLabel: 'Thread A', latestRecordId: 'call-3', callCount: 3, totalTokens: 900 });
    expect(result).toMatchObject({ totalMatchedRows: 1, hasMore: false, nextOffset: null });
  });

  it('accepts unbounded thread-call pages and rejects unknown schemas', () => {
    expect(decodeExploreCalls({
      schema: 'codex-usage-tracker-thread-calls-v1',
      thread_key: 'thread-a',
      rows: [],
      row_count: 0,
      total_matched_rows: 0,
      limit: null,
      offset: 0,
      raw_context_included: false,
    })).toMatchObject({ threadKey: 'thread-a', limit: null, hasMore: false });

    expect(() => decodeExploreCalls({ schema: 'other', rows: [] })).toThrow(ExploreContractError);
  });
});
