import type { CallDetailResult } from '../../api/calls';
import type { CallRow, DashboardModel } from '../../api/types';

export type CallInvestigatorSelection = {
  modelIndex: number;
  activeIndex: number;
  hydratedDetail: CallDetailResult | null;
  call: CallRow | null;
  previous: CallRow | null;
  next: CallRow | null;
  threadCalls: CallRow[];
  positionLabel: string;
};

export function callInvestigatorCallForCurrentUrl(model: DashboardModel, href = window.location.href): CallRow[] {
  const recordId = new URL(href).searchParams.get('record')?.trim();
  if (recordId) {
    const selected = model.calls.find(call => call.id === recordId);
    return selected ? [selected] : [];
  }
  return model.calls[0] ? [model.calls[0]] : [];
}

export function resolveCallInvestigatorSelection({
  calls,
  recordId,
  detail,
}: {
  calls: CallRow[];
  recordId: string;
  detail: CallDetailResult | null;
}): CallInvestigatorSelection {
  const modelIndex = calls.findIndex(call => call.id === recordId);
  const activeIndex = modelIndex >= 0 ? modelIndex : !recordId && calls.length ? 0 : -1;
  const hydratedDetail = detail?.record.id === recordId ? detail : null;
  const call = hydratedDetail?.record ?? (activeIndex >= 0 ? calls[activeIndex] : null);
  const previous = hydratedDetail?.previousRecord ?? (activeIndex > 0 ? calls[activeIndex - 1] : null);
  const next = hydratedDetail?.nextRecord ?? (activeIndex >= 0 && activeIndex < calls.length - 1 ? calls[activeIndex + 1] : null);
  const threadCalls = call ? resolveThreadCalls(calls, call, hydratedDetail) : [];
  const positionLabel = hydratedDetail
    ? 'Hydrated from /api/call'
    : activeIndex >= 0
      ? `${activeIndex + 1} of ${calls.length} loaded calls`
      : 'Record outside loaded snapshot';

  return { modelIndex, activeIndex, hydratedDetail, call, previous, next, threadCalls, positionLabel };
}

function resolveThreadCalls(calls: CallRow[], call: CallRow, hydratedDetail: CallDetailResult | null): CallRow[] {
  const relatedRows = calls.filter(candidate => candidate.thread === call.thread);
  const hydratedRows = [hydratedDetail?.previousRecord, hydratedDetail?.record, hydratedDetail?.nextRecord].filter(isCallRow);
  const byId = new Map<string, CallRow>();
  for (const row of [...relatedRows, ...hydratedRows, call]) {
    byId.set(row.id, row);
  }
  return [...byId.values()].sort(compareInvestigatorCallTimeDescending);
}

function isCallRow(row: CallRow | null | undefined): row is CallRow {
  return Boolean(row?.id);
}

function compareInvestigatorCallTimeDescending(left: CallRow, right: CallRow): number {
  return Date.parse(right.rawTime || right.time) - Date.parse(left.rawTime || left.time);
}
