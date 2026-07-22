import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ConversationalReadiness } from '../../api/types';
import { ConversationalAnalysisStatus } from './ConversationalAnalysisStatus';

const readiness = (state: ConversationalReadiness['state']): ConversationalReadiness => ({
  schema: 'codex-usage-tracker-conversational-readiness-v1',
  state,
  summary: state === 'unknown' ? 'Readiness could not be inspected.' : `State: ${state}`,
  next_action: state === 'ready'
    ? null
    : state === 'restart-required'
      ? 'Restart Codex and open a fresh task to load the plugin tools.'
      : state === 'unavailable'
        ? 'Run `codex-usage-tracker setup`, then `codex-usage-tracker doctor`.'
        : 'Run `codex-usage-tracker doctor` for a bounded diagnosis.',
  evidence: ['MCP config: pass'],
});

describe('ConversationalAnalysisStatus', () => {
  it.each([
    ['ready', /local checks passed/i],
    ['restart-required', /restart.*fresh task/i],
    ['unavailable', /codex-usage-tracker setup.*codex-usage-tracker doctor/i],
    ['unknown', /bounded diagnosis/i],
  ] as const)('renders %s recovery guidance', (state, expected) => {
    render(<ConversationalAnalysisStatus readiness={readiness(state)} />);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it('normalizes an omitted static-export status to unknown and keeps manual fallbacks', () => {
    render(<ConversationalAnalysisStatus />);
    expect(screen.getByText(/could not be determined from this static payload/i)).toBeInTheDocument();
    expect(screen.getByText(/open a live dashboard.*doctor/i)).toBeInTheDocument();
    for (const label of ['Home', 'Explore', 'Limits', 'CLI analyze or query']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it('preserves the exact readiness boundary and server recovery action', () => {
    render(<ConversationalAnalysisStatus readiness={{
      ...readiness('restart-required'),
      summary: 'The local launcher is installed; a fresh Codex task is required for discovery.',
      next_action: 'Restart Codex and open a fresh task to load the plugin tools.',
    }} />);
    expect(screen.getByText('The local launcher is installed; a fresh Codex task is required for discovery.')).toBeInTheDocument();
    expect(screen.getByText('Restart Codex and open a fresh task to load the plugin tools.')).toBeInTheDocument();
    expect(screen.queryByText(/tools are available in this task/i)).not.toBeInTheDocument();
  });
});
