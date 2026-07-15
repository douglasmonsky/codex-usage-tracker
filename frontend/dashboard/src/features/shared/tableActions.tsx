import type { ColumnDef } from '@tanstack/react-table';
import { Copy, Search } from 'lucide-react';

import type { CallRow, ThreadRow } from '../../api/types';
import type { LocalizedText } from '../../app/i18n';
import { useShellI18n } from '../../app/i18nContext';
import { stopRowActionKeyDown } from './rowActionEvents';

type CallActionColumnOptions = {
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink?: (recordId: string) => void;
  labelPrefix?: string;
};

type ThreadActionColumnOptions = {
  onOpenInvestigator: (recordId: string) => void;
  onCopyCallLink?: (recordId: string) => void;
};

export function callInvestigatorRowLabel(call: CallRow, labelPrefix = ''): LocalizedText {
  return {
    template: 'Open call row in investigator for {target}',
    values: { target: callActionTarget(call, labelPrefix) },
  };
}

export function threadInvestigatorRowLabel(thread: ThreadRow): LocalizedText {
  return thread.latestCallId
    ? { template: 'Open thread row latest call in investigator for {thread}', values: { thread: thread.name } }
    : { template: 'No loaded call available for {thread}', values: { thread: thread.name } };
}

export function callActionColumn({
  onOpenInvestigator,
  onCopyCallLink,
  labelPrefix = '',
}: CallActionColumnOptions): ColumnDef<CallRow> {
  return {
    id: 'investigate',
    header: 'Investigate',
    minSize: 276,
    size: 276,
    enableSorting: false,
    cell: info => (
      <CallActionCell
        call={info.row.original}
        labelPrefix={labelPrefix}
        onCopyCallLink={onCopyCallLink}
        onOpenInvestigator={onOpenInvestigator}
      />
    ),
  };
}

export function threadActionColumn({
  onOpenInvestigator,
  onCopyCallLink,
}: ThreadActionColumnOptions): ColumnDef<ThreadRow> {
  return {
    id: 'investigate',
    header: 'Investigate',
    minSize: 276,
    size: 276,
    enableSorting: false,
    cell: info => (
      <ThreadActionCell
        thread={info.row.original}
        onCopyCallLink={onCopyCallLink}
        onOpenInvestigator={onOpenInvestigator}
      />
    ),
  };
}

function CallActionCell({
  call,
  labelPrefix,
  onCopyCallLink,
  onOpenInvestigator,
}: {
  call: CallRow;
  labelPrefix: string;
  onCopyCallLink?: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
}) {
  const i18n = useShellI18n();
  const openLabel = i18n.t('button.open_investigator', 'Open investigator');
  const copyLabel = i18n.t('button.copy_link', 'Copy link');
  const target = callActionTarget(call, labelPrefix);

  return (
    <div className="table-action-group">
      <button
        className="table-action-button"
        type="button"
        aria-label={i18n.formatText(`${openLabel} for {target}`, { target })}
        onKeyDown={stopRowActionKeyDown}
        onClick={event => {
          event.stopPropagation();
          onOpenInvestigator(call.id);
        }}
      >
        <Search size={14} />
        {openLabel}
      </button>
      {onCopyCallLink ? (
        <button
          className="table-action-button"
          type="button"
          aria-label={i18n.formatText(`${copyLabel} for {target}`, { target })}
          onKeyDown={stopRowActionKeyDown}
          onClick={event => {
            event.stopPropagation();
            onCopyCallLink(call.id);
          }}
        >
          <Copy size={14} />
          {copyLabel}
        </button>
      ) : null}
    </div>
  );
}

function ThreadActionCell({
  thread,
  onCopyCallLink,
  onOpenInvestigator,
}: {
  thread: ThreadRow;
  onCopyCallLink?: (recordId: string) => void;
  onOpenInvestigator: (recordId: string) => void;
}) {
  const i18n = useShellI18n();
  const openLabel = i18n.translateText('Open');
  const copyLabel = i18n.translateText('Copy');

  return (
    <div className="table-action-group">
      <button
        className="table-action-button"
        type="button"
        aria-label={i18n.formatText('Open investigator for latest call in {thread}', { thread: thread.name })}
        onKeyDown={stopRowActionKeyDown}
        onClick={event => {
          event.stopPropagation();
          if (thread.latestCallId) onOpenInvestigator(thread.latestCallId);
        }}
        disabled={!thread.latestCallId}
      >
        <Search size={14} />
        {openLabel}
      </button>
      {onCopyCallLink ? (
        <button
          className="table-action-button"
          type="button"
          aria-label={i18n.formatText('Copy link for latest call in {thread}', { thread: thread.name })}
          onKeyDown={stopRowActionKeyDown}
          onClick={event => {
            event.stopPropagation();
            if (thread.latestCallId) onCopyCallLink(thread.latestCallId);
          }}
          disabled={!thread.latestCallId}
        >
          <Copy size={14} />
          {copyLabel}
        </button>
      ) : null}
    </div>
  );
}

function callActionTarget(call: CallRow, labelPrefix: string): string {
  return `${labelPrefix} ${call.thread} ${call.model}`.trim();
}
