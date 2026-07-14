import { describe, expect, it } from 'vitest';

import {
  compressionProfileQueryOptions,
  type CompressionQueryRequest,
} from './compressionQueries';

describe('Compression Lab query options', () => {
  it('keys profiles by credential-free source and complete semantic scope', () => {
    const request: CompressionQueryRequest = {
      runtime: { apiToken: 'private-token', contextApiEnabled: false, fileMode: false },
      includeArchived: false,
      since: '2026-07-01T00:00:00Z',
      sourceKey: 'fixture-source',
      sourceRevision: 'revision-1',
    };
    const key = compressionProfileQueryOptions(request).queryKey;

    expect(JSON.stringify(key)).not.toContain('private-token');
    expect(compressionProfileQueryOptions({ ...request }).queryKey).toEqual(key);
    expect(compressionProfileQueryOptions({ ...request, sourceRevision: 'revision-2' }).queryKey)
      .not.toEqual(key);
    expect(compressionProfileQueryOptions({ ...request, includeArchived: true }).queryKey)
      .not.toEqual(key);
    expect(compressionProfileQueryOptions({ ...request, since: null }).queryKey)
      .not.toEqual(key);
  });
});
