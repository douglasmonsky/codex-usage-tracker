import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import type { ConversationalReadiness } from '../../api/types';
import { ConversationalAnalysisStatus } from './ConversationalAnalysisStatus';

const readiness = (state: ConversationalReadiness['state']): ConversationalReadiness => ({
  schema: 'codex-usage-tracker-conversational-readiness-v1',
  state,
  summary: state === 'unknown' ? 'Readiness could not be inspected.' : `State: ${state}`,
  next_action: state === 'ready' ? null : `Action for ${state}`,
  evidence: ['MCP config: pass'],
});

describe('ConversationalAnalysisStatus', () => {
  it.each([
    ['ready', /local checks passed/i],
    ['restart-required', /restart.*fresh task/i],
    ['unavailable', /codex-usage-tracker setup.*codex-usage-tracker doctor/i],
    ['unknown', /could not be determined/i],
  ] as const)('renders %s recovery guidance', (state, expected) => {
    render(<ConversationalAnalysisStatus readiness={readiness(state)} />);
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it('normalizes an omitted static-export status to unknown and keeps manual fallbacks', () => {
    render(<ConversationalAnalysisStatus />);
    expect(screen.getAllByText(/could not be determined/i)).toHaveLength(2);
    for (const label of ['Calls', 'Threads', 'Limits', 'Diagnostics', 'Advanced experimental controls']) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });
});
