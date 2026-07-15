import { describe, expect, it } from 'vitest';

import { allowanceAnalysisPollInterval, allowanceStatusPollInterval } from './allowancePolling';

describe('allowance polling policy', () => {
  it('polls fresh and aging status every 30 seconds', () => {
    expect(allowanceStatusPollInterval('fresh', 0, true)).toBe(30_000);
    expect(allowanceStatusPollInterval('aging', 0, true)).toBe(30_000);
  });

  it('polls stale, partial, empty, and not-yet-loaded status every 60 seconds', () => {
    expect(allowanceStatusPollInterval('stale', 0, true)).toBe(60_000);
    expect(allowanceStatusPollInterval('partial', 0, true)).toBe(60_000);
    expect(allowanceStatusPollInterval('empty', 0, true)).toBe(60_000);
    expect(allowanceStatusPollInterval(undefined, 0, true)).toBe(60_000);
  });

  it('pauses in hidden tabs and caps transient failure backoff at five minutes', () => {
    expect(allowanceStatusPollInterval('fresh', 0, false)).toBe(false);
    expect(allowanceStatusPollInterval('fresh', 1, true)).toBe(60_000);
    expect(allowanceStatusPollInterval('fresh', 20, true)).toBe(300_000);
  });

  it('polls analysis jobs at 500ms only while work is active and visible', () => {
    expect(allowanceAnalysisPollInterval('pending', true)).toBe(500);
    expect(allowanceAnalysisPollInterval('queued', true)).toBe(500);
    expect(allowanceAnalysisPollInterval('running', true)).toBe(500);
    expect(allowanceAnalysisPollInterval('completed', true)).toBe(false);
    expect(allowanceAnalysisPollInterval('failed', true)).toBe(false);
    expect(allowanceAnalysisPollInterval('running', false)).toBe(false);
  });
});
