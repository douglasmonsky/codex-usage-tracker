import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { buildDashboardTarget, type DashboardTarget } from '../app/dashboardTargets';
import { investigatorEvidenceDashboardTarget } from '../features/investigator/InvestigatorPage';
import { DashboardEvidenceActions } from './DashboardEvidenceActions';

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe('DashboardEvidenceActions', () => {
  it('opens only a loopback evidence target and copies a strict aggregate-only prompt', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    const onStatus = vi.fn();
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const target = buildDashboardTarget({
      view: 'call',
      record_id: 'record-123',
      history: 'all',
      privacy_mode: 'strict',
      service_origin: 'http://127.0.0.1:47821',
    });

    render(
      <DashboardEvidenceActions
        target={target}
        question={`Review ${['s', 'k-', 'abcdefghijklmnopqrstuvwxyz123456'].join('')} at /Users/private [redacted client-name]`}
        onStatus={onStatus}
      />,
    );

    const link = screen.getByRole('link', { name: 'Open evidence' });
    expect(link).toHaveAttribute('href', target.absolute_url);
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');

    fireEvent.click(screen.getByRole('button', { name: 'Copy investigation prompt' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    const prompt = String(writeText.mock.calls[0]?.[0]);
    expect(prompt).toContain('record-123');
    expect(prompt).toContain('history=all');
    expect(prompt).toContain(target.relative_url);
    expect(prompt).not.toMatch(/sk-|\/Users\/private|client-name|\[redacted/i);
    expect(onStatus).toHaveBeenCalledWith('Investigation prompt copied');
  });

  it('blocks non-loopback absolute targets and gives launch guidance', () => {
    const onStatus = vi.fn();
    const target = {
      ...buildDashboardTarget({ view: 'reports' }),
      absolute_url: 'https://example.com/private',
    } satisfies DashboardTarget;

    render(<DashboardEvidenceActions target={target} question="Review this report" onStatus={onStatus} />);

    expect(screen.queryByRole('link', { name: 'Open evidence' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open evidence' }));
    expect(onStatus).toHaveBeenCalledWith(
      'Start the local dashboard first: codex-usage-tracker serve-dashboard --open',
    );
  });

  it('keeps ordinary product vocabulary in a non-strict prompt', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const target = buildDashboardTarget({ view: 'reports', privacy_mode: 'normal' });

    render(
      <DashboardEvidenceActions
        target={target}
        question="Where is avoidable token waste concentrated?"
        onStatus={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Copy investigation prompt' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('avoidable token waste'));
  });

  it.each([
    'Review /home/private/report.txt',
    'Review /tmp/private-report.txt',
    `Review ${['g', 'hp_', 'abcdefghijklmnopqrstuvwxyz1234567890'].join('')}`,
    `authorization: ${['Bear', 'er ', 'abcdefghijklmnopqrstuvwxyz123456'].join('')}`,
    `access_token=${['private', '-value-1234567890'].join('')}`,
  ])('drops unsafe non-strict caller text: %s', async question => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const target = buildDashboardTarget({ view: 'reports', privacy_mode: 'normal' });

    render(<DashboardEvidenceActions target={target} question={question} onStatus={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Copy investigation prompt' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(String(writeText.mock.calls[0]?.[0])).not.toContain(question);
  });

  it('does not claim an unstable finding ordinal when canonical evidence is unavailable', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    const target = investigatorEvidenceDashboardTarget(undefined, false, null);

    render(
      <DashboardEvidenceActions
        target={target}
        question="Investigate aggregate evidence for finding 2."
        onStatus={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Copy investigation prompt' }));
    await waitFor(() => expect(writeText).toHaveBeenCalledTimes(1));
    expect(target.relative_url).not.toContain('finding=');
    expect(String(writeText.mock.calls[0]?.[0])).not.toContain('finding=');
  });
});
