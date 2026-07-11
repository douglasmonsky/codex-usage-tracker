import { describe, expect, it } from 'vitest';

import { fileEvidenceRows, toolEvidenceRows } from './diagnosticEvidence';

describe('diagnostic explorer evidence adapters', () => {
  it('normalizes tool facts into stable evidence rows', () => {
    const rows = toolEvidenceRows({
      rows: [{
        fact_type: 'tool',
        fact_name: 'rg',
        occurrences: 12,
        associated_calls: 4,
        associated_uncached_input_tokens: 900,
        associated_total_tokens: 1_400,
        avg_cache_ratio: 0.35,
        largest_record_id: 'call-4',
      }],
    });

    expect(rows[0]).toMatchObject({
      id: 'tool:rg', name: 'rg', occurrences: 12, associatedCalls: 4,
      uncachedInputTokens: 900, totalTokens: 1_400, cachePct: 35, representativeRecordId: 'call-4',
    });
  });

  it('joins read and modification snapshots by safe path hash', () => {
    const rows = fileEvidenceRows(
      { top_paths: [{ path_hash: 'hash-a', path_label: 'src/a.ts', read_events: 8, allocated_output_token_sum: 2_400, representative_record_id: 'read-call' }] },
      { top_paths: [{ path_hash: 'hash-a', path_label: 'src/a.ts', modification_events: 3, representative_record_id: 'write-call' }] },
    );

    expect(rows).toEqual([expect.objectContaining({
      id: 'hash-a', pathHash: 'hash-a', pathLabel: 'src/a.ts', readEvents: 8,
      allocatedOutputTokens: 2_400, modificationEvents: 3,
      readRecordId: 'read-call', modificationRecordId: 'write-call', representativeRecordId: 'read-call',
    })]);
  });
});
