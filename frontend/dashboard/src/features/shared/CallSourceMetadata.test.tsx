import { describe, expect, it } from 'vitest';
import type { CallRow } from '../../api/types';
import { render, screen, within } from '../../test-utils/appTestHarness';
import { CallSourceMetadata } from './CallSourceMetadata';

describe('CallSourceMetadata', () => {
  it('uses the shared source-line fallback for missing source metadata', () => {
    render(<CallSourceMetadata call={callWithoutSourceLine()} />);

    const card = screen.getByText('Call Source').closest('.call-source-card');
    expect(card).not.toBeNull();
    const panel = within(card as HTMLElement);

    expect(panel.getAllByText('Not available').length).toBeGreaterThan(0);
    expect(panel.getByText('Source line')).toBeInTheDocument();
    expect(panel.getByText('Project tags')).toBeInTheDocument();
    expect(panel.getAllByText('None').length).toBeGreaterThan(0);
  });
});

function callWithoutSourceLine(): CallRow {
  return {
    project: '',
    projectRelativeCwd: '',
    cwd: '',
    projectTags: [],
    threadAttachmentLabel: '',
    threadSource: '',
    subagentType: '',
    agentRole: '',
    agentNickname: '',
    sourceFile: '',
    lineNumber: null,
    initiator: '',
    initiatorReason: '',
    sessionId: '',
    turnId: '',
    parentThread: '',
    parentSessionId: '',
    parentSessionUpdatedAt: '',
    gitBranch: '',
    gitRemoteLabel: '',
    gitRemoteHash: '',
    usageCreditNote: '',
  } as unknown as CallRow;
}
