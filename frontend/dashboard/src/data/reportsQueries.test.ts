import { describe, expect, it } from 'vitest';

import { reportsQueryOptions, type ReportsQueryRequest } from './reportsQueries';

describe('reports query options', () => {
  it('keys report packs by credential-free source and complete semantic scope', () => {
    const request: ReportsQueryRequest = {
      runtime: { apiToken: 'private-token', contextApiEnabled: false, fileMode: false },
      includeArchived: false,
      loadWindow: 'all',
      limit: 0,
      evidenceLimit: 8,
      sourceKey: 'fixture-source',
      sourceRevision: 'revision-1',
    };
    const key = reportsQueryOptions(request).queryKey;

    expect(JSON.stringify(key)).not.toContain('private-token');
    expect(reportsQueryOptions({ ...request }).queryKey).toEqual(key);
    expect(reportsQueryOptions({ ...request, sourceRevision: 'revision-2' }).queryKey).not.toEqual(key);
    expect(reportsQueryOptions({ ...request, includeArchived: true }).queryKey).not.toEqual(key);
    expect(reportsQueryOptions({ ...request, loadWindow: 'rows', limit: 500 }).queryKey).not.toEqual(key);
    expect(reportsQueryOptions({ ...request, evidenceLimit: 20 }).queryKey).not.toEqual(key);
  });
});
