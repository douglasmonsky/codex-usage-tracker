import type { CallRow } from '../../api/types';

export function CallSourceMetadata({ call }: { call: CallRow }) {
  return (
    <div className="call-source-card composition-card">
      <div className="composition-head">
        <strong>Call Source</strong>
        <span>{sourceLine(call)}</span>
      </div>
      <dl className="detail-list compact">
        <DetailRow label="Project" value={call.project || 'Unknown'} />
        <DetailRow label="Project path" value={call.projectRelativeCwd || call.cwd || '.'} />
        <DetailRow label="Project tags" value={call.projectTags.length ? call.projectTags.join(', ') : 'None'} />
        <DetailRow label="Thread attachment" value={call.threadAttachmentLabel || 'Direct thread'} />
        <DetailRow label="Thread source" value={call.threadSource || 'user'} />
        <DetailRow label="Subagent type" value={call.subagentType || 'None'} />
        <DetailRow label="Agent role" value={call.agentRole || 'None'} />
        <DetailRow label="Agent nickname" value={call.agentNickname || 'None'} />
        <DetailRow label="Source line" value={sourceLine(call)} />
        <DetailRow label="Initiated by" value={call.initiator || 'unknown'} />
        <DetailRow label="Initiator reason" value={call.initiatorReason || 'Not reported'} />
        <DetailRow label="Session" value={call.sessionId || 'Not available'} />
        <DetailRow label="Turn" value={call.turnId || 'None'} />
        <DetailRow label="Parent thread" value={call.parentThread || 'None'} />
        <DetailRow label="Parent session" value={call.parentSessionId || 'None'} />
        <DetailRow label="Parent updated" value={formatTimestamp(call.parentSessionUpdatedAt)} />
        <DetailRow label="Working directory" value={call.cwd || 'Not available'} />
        <DetailRow label="Git branch" value={call.gitBranch || 'Not available'} />
        <DetailRow label="Git remote" value={call.gitRemoteLabel || 'Not available'} />
        <DetailRow label="Git hash" value={call.gitRemoteHash || 'Not available'} />
        <DetailRow label="Credit note" value={call.usageCreditNote || 'None'} />
      </dl>
    </div>
  );
}

function formatTimestamp(value: string): string {
  if (!value) return 'None';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function sourceLine(call: CallRow): string {
  if (!call.sourceFile) return 'Source line not reported';
  return `${call.sourceFile}${call.lineNumber ? `:${call.lineNumber}` : ''}`;
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
