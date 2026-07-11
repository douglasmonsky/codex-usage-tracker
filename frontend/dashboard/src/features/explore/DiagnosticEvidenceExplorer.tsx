import type { ReactNode } from 'react';

import type { ContextRuntime } from '../../api/types';
import { FileEvidenceExplorer } from './FileEvidenceExplorer';
import { ToolEvidenceExplorer } from './ToolEvidenceExplorer';

type DiagnosticEvidenceExplorerProps = {
  mode: 'tools' | 'files';
  contextRuntime: ContextRuntime;
  globalQuery: string;
  onCopyCallLink: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
  sourceRevision: string;
  workspaceSwitcher: ReactNode;
};

export function DiagnosticEvidenceExplorer(props: DiagnosticEvidenceExplorerProps) {
  return props.mode === 'tools'
    ? <ToolEvidenceExplorer {...props} />
    : <FileEvidenceExplorer {...props} />;
}
