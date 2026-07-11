import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { VisualContractLab } from './VisualContractLab';

describe('VisualContractLab', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/');
    Object.defineProperty(window, 'scrollTo', {
      configurable: true,
      value: vi.fn(),
    });
  });

  it('opens on the answer-first overview contract', () => {
    render(<VisualContractLab />);

    expect(screen.getByRole('heading', { level: 1, name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByText('Two threads account for most avoidable context reloads')).toBeInTheDocument();
    expect(screen.getByRole('region', { name: /Relative usage history/ })).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('keeps table selection visible before opening the full call investigator', () => {
    render(<VisualContractLab />);

    fireEvent.click(screen.getAllByRole('button', { name: /Explore/ })[0]);
    const callsTable = screen.getByLabelText('Calls table. Scroll horizontally for more columns.');
    fireEvent.click(within(callsTable).getByRole('button', { name: /Parser fixture hardening call-1034/ }));

    const inspector = screen.getByLabelText('Selected call inspector');
    expect(within(inspector).getByText('Parser fixture hardening')).toBeInTheDocument();
    fireEvent.click(within(inspector).getByRole('button', { name: /Full investigator/ }));
    expect(screen.getByRole('heading', { level: 1, name: 'Parser fixture hardening' })).toBeInTheDocument();
  });

  it('applies an explicit uncapped all-history scope', () => {
    render(<VisualContractLab />);

    fireEvent.click(screen.getByRole('button', { name: /5,000 loaded/ }));
    const dialog = screen.getByRole('dialog', { name: 'Data scope' });
    fireEvent.change(within(dialog).getByLabelText('History'), { target: { value: 'all' } });
    fireEvent.click(within(dialog).getByRole('checkbox', { name: 'No row cap' }));
    fireEvent.click(within(dialog).getByRole('button', { name: 'Apply scope' }));

    expect(screen.getByRole('status')).toHaveTextContent('All rows / all history applied');
    expect(screen.getByRole('button', { name: /All rows/ })).toBeInTheDocument();
  });

  it('distinguishes weekly allowance evidence from five-hour context', () => {
    render(<VisualContractLab />);

    fireEvent.click(screen.getAllByRole('button', { name: /Limits/ })[0]);
    expect(screen.getByRole('heading', { level: 1, name: 'Limits' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '5-hour' }));
    expect(screen.getByRole('heading', { name: '5-hour rolling context' })).toBeInTheDocument();
  });

  it('routes global evidence search into the explorer', () => {
    render(<VisualContractLab />);

    fireEvent.change(screen.getByRole('textbox', { name: 'Search dashboard' }), {
      target: { value: 'cache reuse' },
    });
    fireEvent.submit(screen.getByRole('search'));

    expect(screen.getByRole('heading', { level: 1, name: 'Calls' })).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Searching loaded evidence for “cache reuse”');
  });

  it.each([
    ['loading', 'Building the local evidence index'],
    ['empty', 'No calls match this data scope'],
    ['stale', 'Showing current cached evidence while source updates load'],
    ['partial', 'Partial evidence is available'],
    ['error', 'The latest source delta could not be read'],
  ])('renders the %s contract state without a blank chart', (state, expectedText) => {
    render(<VisualContractLab />);

    fireEvent.click(screen.getByRole('button', { name: /5,000 loaded/ }));
    fireEvent.change(screen.getByLabelText('Preview state'), { target: { value: state } });

    expect(screen.getByText(expectedText)).toBeInTheDocument();
  });

  it('restores a shareable scenario and state from the lab URL', () => {
    window.history.replaceState(null, '', '/?lab=visual-contract&view=limits&state=partial');
    render(<VisualContractLab />);

    expect(screen.getByRole('heading', { level: 1, name: 'Limits' })).toBeInTheDocument();
    expect(screen.getByText('Partial evidence is available')).toBeInTheDocument();
  });
});
