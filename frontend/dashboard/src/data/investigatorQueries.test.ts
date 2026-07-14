import { describe, expect, it } from 'vitest';

import {
  investigatorAgenticQueryOptions,
  investigatorSnapshotQueryOptions,
  investigatorWalkQueryOptions,
  type InvestigatorAgenticQueryRequest,
} from './investigatorQueries';

const request: InvestigatorAgenticQueryRequest = {
  runtime: {
    apiToken: 'private-investigator-token',
    contextApiEnabled: true,
    fileMode: false,
  },
  includeArchived: false,
  sourceKey: 'fixture-source',
  sourceRevision: 'revision-1',
  evidenceLimit: 8,
};

describe('investigator query options', () => {
  it('keys agentic reports by credential-free source and complete scope', () => {
    const key = investigatorAgenticQueryOptions(request).queryKey;

    expect(JSON.stringify(key)).not.toContain('private-investigator-token');
    expect(investigatorAgenticQueryOptions({ ...request }).queryKey).toEqual(key);
    expect(investigatorAgenticQueryOptions({ ...request, sourceRevision: 'revision-2' }).queryKey)
      .not.toEqual(key);
    expect(investigatorAgenticQueryOptions({ ...request, includeArchived: true }).queryKey)
      .not.toEqual(key);
    expect(investigatorAgenticQueryOptions({ ...request, evidenceLimit: 20 }).queryKey)
      .not.toEqual(key);
    expect(investigatorAgenticQueryOptions({ ...request, goal: 'shell_churn' }).queryKey)
      .not.toEqual(key);
  });

  it('keys each diagnostic snapshot independently', () => {
    const overviewKey = investigatorSnapshotQueryOptions({
      ...request,
      snapshotKey: 'overview',
    }).queryKey;
    const commandsKey = investigatorSnapshotQueryOptions({
      ...request,
      snapshotKey: 'commands',
    }).queryKey;

    expect(overviewKey).not.toEqual(commandsKey);
    expect(JSON.stringify(overviewKey)).not.toContain('private-investigator-token');
  });

  it('keys local walks by normalized question and scan controls', () => {
    const key = investigatorWalkQueryOptions({
      ...request,
      question: '  Where is waste concentrated?  ',
      evidenceLimit: 6,
      minOccurrences: 2,
    }).queryKey;

    expect(JSON.stringify(key)).not.toContain('private-investigator-token');
    expect(investigatorWalkQueryOptions({
      ...request,
      question: 'Where is waste concentrated?',
      evidenceLimit: 6,
      minOccurrences: 2,
    }).queryKey).toEqual(key);
    expect(investigatorWalkQueryOptions({
      ...request,
      question: 'Which files are repeatedly rediscovered?',
    }).queryKey).not.toEqual(key);
    expect(investigatorWalkQueryOptions({
      ...request,
      question: 'Where is waste concentrated?',
      minOccurrences: 5,
    }).queryKey).not.toEqual(key);
  });
});
