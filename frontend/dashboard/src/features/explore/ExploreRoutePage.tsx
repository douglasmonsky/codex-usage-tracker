import { useEffect, useState } from 'react';

import { CallsPage, type CallsPageProps } from '../calls/CallsPage';
import { DiagnosticEvidenceExplorer } from './DiagnosticEvidenceExplorer';
import {
  ExploreWorkspaceSwitcher,
  exploreWorkspaceFromSearch,
  exploreWorkspaceUrl,
  type ExploreWorkspaceId,
} from './ExploreWorkspaceSwitcher';

type ExploreRoutePageProps = CallsPageProps & {
  onNavigateView: (view: 'calls' | 'threads') => void;
};

export function ExploreRoutePage({ onNavigateView, ...props }: ExploreRoutePageProps) {
  const [workspace, setWorkspace] = useState(() => exploreWorkspaceFromSearch());

  useEffect(() => {
    const syncWorkspace = () => setWorkspace(exploreWorkspaceFromSearch());
    window.addEventListener('popstate', syncWorkspace);
    return () => window.removeEventListener('popstate', syncWorkspace);
  }, []);

  function selectWorkspace(nextWorkspace: ExploreWorkspaceId) {
    if (nextWorkspace === 'threads') {
      onNavigateView('threads');
      return;
    }
    window.history.pushState(null, '', exploreWorkspaceUrl(nextWorkspace));
    setWorkspace(nextWorkspace);
  }

  const workspaceSwitcher = <ExploreWorkspaceSwitcher current={workspace} onValueChange={selectWorkspace} />;
  if (workspace === 'tools' || workspace === 'files') {
    return (
      <DiagnosticEvidenceExplorer
        mode={workspace}
        contextRuntime={props.contextRuntime}
        globalQuery={props.globalQuery}
        onCopyCallLink={props.onCopyCallLink}
        onOpenInvestigator={props.onOpenInvestigator}
        sourceRevision={props.sourceRevision ?? ''}
        workspaceSwitcher={workspaceSwitcher}
      />
    );
  }
  return <CallsPage {...props} workspaceSwitcher={workspaceSwitcher} />;
}
