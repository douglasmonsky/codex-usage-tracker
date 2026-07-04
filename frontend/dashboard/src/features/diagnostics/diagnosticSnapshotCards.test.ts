import { describe, expect, it } from 'vitest';
import type { DiagnosticSnapshotDefinition, DiagnosticSnapshotPayload } from '../../api/diagnostics';
import { snapshotCard } from './diagnosticSnapshotCards';

const toolOutputDefinition: DiagnosticSnapshotDefinition = {
  key: 'toolOutput',
  title: 'Tool Output',
  path: '/api/diagnostics/tool-output',
  refreshPath: '/api/diagnostics/tool-output/refresh',
};

const commandsDefinition: DiagnosticSnapshotDefinition = {
  key: 'commands',
  title: 'Commands',
  path: '/api/diagnostics/commands',
  refreshPath: '/api/diagnostics/commands/refresh',
};

describe('diagnostic snapshot cards', () => {
  it('ports legacy stored snapshot metadata into card subtitles', () => {
    const card = snapshotCard(toolOutputDefinition, {
      status: 'ready',
      snapshot: {
        computed_at: '2026-07-03T12:00:00Z',
        history_scope: 'all',
        source_logs_scanned: 12,
        usage_rows_scanned: 34,
      },
      summary: {},
      functions: [],
    } as DiagnosticSnapshotPayload);

    expect(card.subtitle).toContain('Computed Jul 3, 8:00 AM');
    expect(card.subtitle).toContain('history all');
    expect(card.subtitle).toContain('logs scanned 12');
    expect(card.subtitle).toContain('rows scanned 34');
  });

  it('shows history scope when a live snapshot section has no stored snapshot yet', () => {
    const card = snapshotCard(toolOutputDefinition, {
      status: 'missing',
      history_scope: 'all',
      summary: {},
      functions: [],
    } as DiagnosticSnapshotPayload);

    expect(card.subtitle).toBe('history all · no stored snapshot');
  });

  it('preserves representative record ids from live aggregate rows', () => {
    const card = snapshotCard(toolOutputDefinition, {
      status: 'ready',
      summary: {},
      functions: [
        {
          function: 'functions.exec_command',
          calls: 2,
          original_token_sum: 1234,
          largest_record_id: 'largest-live-call',
        },
      ],
    } as DiagnosticSnapshotPayload);

    expect(card.rows[0]).toMatchObject({
      label: 'functions.exec_command',
      recordId: 'largest-live-call',
    });
  });

  it('uses the first aggregate record id when snapshot rows expose record lists', () => {
    const card = snapshotCard(commandsDefinition, {
      status: 'ready',
      summary: {},
      commands: [
        {
          root: 'git',
          total: 3,
          children: [],
          record_ids: ['command-call-1', 'command-call-2'],
        },
      ],
    } as DiagnosticSnapshotPayload);

  expect(card.rows[0]).toMatchObject({
   label: 'git',
   recordId: 'command-call-1',
  });
 });

 it('preserves command child breakdowns from live aggregate snapshot rows', () => {
  const card = snapshotCard(commandsDefinition, {
   status: 'ready',
   summary: {},
   commands: [
    {
     root: 'git',
     total: 5,
     children: [
      { child: 'status', count: 3 },
      { child: 'diff', count: 2 },
     ],
    },
   ],
  } as DiagnosticSnapshotPayload);

  expect(card.rows[0]).toMatchObject({
   label: 'git',
   detail: '2 child commands',
   value: '5',
   children: [
    { label: 'status', value: '3' },
    { label: 'diff', value: '2' },
   ],
  });
 });
});
