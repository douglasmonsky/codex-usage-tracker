import type { ContextRuntime, DashboardModel } from '../../api/types';
import { CallInvestigatorPage } from '../call-investigator/CallInvestigatorPage';

type CallEvidenceProps = {
  model: DashboardModel;
  recordId: string;
  contextRuntime: ContextRuntime;
  onContextApiEnabledChange: (enabled: boolean) => void;
  onNavigateRecord: (recordId: string) => void;
  onCopyCallLink: (recordId: string) => void;
  onBack: () => void;
  backLabel: string;
};

export function CallEvidence(props: CallEvidenceProps) {
  return (
    <CallInvestigatorPage
      model={props.model}
      recordId={props.recordId}
      contextRuntime={props.contextRuntime}
      onContextApiEnabledChange={props.onContextApiEnabledChange}
      onNavigateRecord={props.onNavigateRecord}
      onCopyCallLink={props.onCopyCallLink}
      onBackToCalls={props.onBack}
      backLabel={props.backLabel}
    />
  );
}
