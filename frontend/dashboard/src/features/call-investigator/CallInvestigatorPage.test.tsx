import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { fixtureModel } from '../../test-fixtures/dashboardFixture';
import { CallInvestigatorPage } from './CallInvestigatorPage';

describe('CallInvestigatorPage compatibility surface', () => {
  it('keeps aggregate call evidence and explicit raw-context gating available through 0.23', () => {
    render(
      <CallInvestigatorPage
        model={fixtureModel}
        recordId="fixture-call-0"
        contextRuntime={{ apiToken: 'local-token', contextApiEnabled: false, fileMode: false }}
        onContextApiEnabledChange={vi.fn()}
        onNavigateRecord={vi.fn()}
        onCopyCallLink={vi.fn()}
        onBackToCalls={vi.fn()}
        backLabel="Back to Explore"
      />,
    );

    expect(screen.getByRole('heading', { name: 'Call Investigator' })).toBeInTheDocument();
    expect(screen.getByText('Aggregate only')).toBeInTheDocument();
    expect(screen.getByText('Raw context gated')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Show turn log evidence' })).toBeInTheDocument();
  });
});
