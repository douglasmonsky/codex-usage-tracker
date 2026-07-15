import { describe, expect, it } from 'vitest';

import type { CallRow } from '../../api/types';
import { callColumns, callCsvColumns, callSignalPucks, callTimestampMs } from './tables';
import { rowsToCsv } from './exportCsv';

describe('call CSV columns', () => {
  it('exports legacy diagnostic source and pricing fields', () => {
    const row: CallRow = {
      id: 'record-csv-1',
      rawTime: '2026-07-01T12:00:00Z',
      eventTimestamp: '2026-07-01T12:00:00Z',
      callStartedAt: '2026-07-01T11:59:30Z',
      time: 'Jul 1',
      thread: 'csv-thread',
      model: 'codex-1',
      effort: 'high',
      input: 1000,
      output: 200,
      reasoningOutput: 75,
      totalTokens: 1200,
      cachedInput: 400,
      uncachedInput: 600,
      cachedPct: 40,
      cost: 0.123456,
      credits: 4.5,
      duration: '2m 0s',
      durationSeconds: 120,
      previousCallGap: '5m 0s',
      previousCallEventTimestamp: '2026-07-01T11:54:30Z',
      previousCallGapSeconds: 300,
      initiator: 'assistant',
      initiatorReason: 'tool-driven continuation',
      initiatorConfidence: 'high',
      fast: false,
      usageCreditConfidence: 'credit-estimated',
      usageCreditModel: 'codex-1',
      usageCreditSource: 'rate-card',
      usageCreditFetchedAt: '2026-07-01T11:00:00Z',
      usageCreditTier: 'pro',
      usageCreditNote: 'estimated mapping',
      pricingModel: 'codex-1-pricing',
      pricingEstimated: true,
      signal: 'cache miss',
      recommendation: 'Compare fresh input',
      tags: ['uncached', 'high-cost'],
      sessionId: 'session-csv',
      turnId: 'turn-csv',
      parentSessionId: 'parent-session-csv',
      parentSessionUpdatedAt: '2026-07-01T11:59:00Z',
      parentThread: 'parent-thread-csv',
      threadAttachmentLabel: 'spawned child',
      threadSource: 'subagent',
      subagentType: 'analysis',
      agentRole: 'reviewer',
      agentNickname: 'usage reviewer',
      project: 'usage-tracker',
      projectRelativeCwd: 'frontend/dashboard',
      projectTags: ['dashboard'],
      cwd: '/work/codex-usage-tracker',
      sourceFile: '/logs/session.jsonl',
      lineNumber: 42,
      gitBranch: 'experiment/frontend-rewrite',
      gitRemoteLabel: 'origin',
      gitRemoteHash: 'abc123',
      contextWindowPct: 62.5,
      modelContextWindow: 200000,
      cumulativeTotalTokens: 123456,
      estimatedCacheSavings: 0.987654,
      efficiencyFlags: ['cache-drop', 'context-heavy'],
    };

    const csv = rowsToCsv([row], callCsvColumns);
    const [header, values] = csv.split('\n');
    const headers = header.split(',');

    expect(header).toContain('record_id');
    expect(headers.slice(0, 6)).toEqual([
      'timestamp',
      'thread',
      'call_started_at',
      'call_duration_seconds',
      'previous_call_event_timestamp',
      'previous_call_delta_seconds',
    ]);
    expect(header).toContain('source_file');
    expect(header).toContain('call_started_at');
    expect(header).toContain('previous_call_event_timestamp');
    expect(header).toContain('pricing_model');
expect(header).toContain('usage_credit_confidence');
expect(header).toContain('thread_attachment');
expect(header).toContain('model_context_window');
    expect(values).toContain('record-csv-1');
    expect(values).toContain('/logs/session.jsonl');
    expect(values.split(',').slice(0, 3)).toEqual([
      '2026-07-01T12:00:00Z',
      'csv-thread',
      '2026-07-01T11:59:30Z',
    ]);
    expect(values).toContain('2026-07-01T11:59:30Z');
    expect(values).toContain('2026-07-01T11:54:30Z');
    expect(values).toContain('codex-1-pricing');
    expect(values).toContain('credit-estimated');
    expect(values).toContain('spawned child');
    expect(values).toContain('cache-drop|context-heavy');
  });
});

describe('call table columns', () => {
  it('sorts time by raw timestamps instead of formatted AM/PM labels', () => {
    const noonCall = {
      id: 'noon-call',
      time: '12:00 PM',
      rawTime: '2026-07-14T12:00:00-04:00',
    } as CallRow;
    const eveningCall = {
      id: 'evening-call',
      time: '7:00 PM',
      rawTime: '2026-07-14T19:00:00-04:00',
    } as CallRow;
    const timeColumn = callColumns.find(column => column.id === 'time');

    expect(callTimestampMs(eveningCall)).toBeGreaterThan(callTimestampMs(noonCall));
    expect(timeColumn).toBeDefined();
    expect(timeColumn && 'accessorFn' in timeColumn ? timeColumn.accessorFn?.(eveningCall, 0) : null).toBeGreaterThan(
      timeColumn && 'accessorFn' in timeColumn ? Number(timeColumn.accessorFn?.(noonCall, 0)) : Number.NaN,
    );
  });
});

describe('call signal pucks', () => {
  it('ports legacy compact multi-signal labels without duplicating aggregate noise', () => {
    const call = {
      signal: 'cache-risk',
      efficiencyFlags: ['cache-risk', 'context-heavy', 'high-cost', 'reasoning-spike'],
    } as CallRow;

    const pucks = callSignalPucks(call);

    expect(pucks.visible.map(puck => puck.shortLabel)).toEqual(['CACHE', 'CTX', '$']);
    expect(pucks.hidden.map(puck => puck.shortLabel)).toEqual(['RSN']);
    expect(pucks.visible.map(puck => puck.label)).toEqual(['Cache Risk', 'Context Heavy', 'High Cost']);
  });
});
