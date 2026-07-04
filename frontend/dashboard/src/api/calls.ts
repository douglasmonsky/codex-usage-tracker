import { usageRowToCall } from './client';
import type { CallRow, ContextRuntime, UsageRow } from './types';

export type CallDetailPayload = {
  schema?: string;
  record?: UsageRow;
  previous_record?: UsageRow | null;
  next_record?: UsageRow | null;
  adjacent_records?: UsageRow[];
  previous_record_id?: string;
  next_record_id?: string;
  raw_context_included?: boolean;
};

export type CallDetailResult = {
  record: CallRow;
  previousRecord: CallRow | null;
  nextRecord: CallRow | null;
  adjacentRecords: CallRow[];
  rawPayload: CallDetailPayload;
};

const callDetailInFlightByKey = new Map<string, Promise<CallDetailResult>>();

export function loadCallDetail(recordId: string, runtime: ContextRuntime): Promise<CallDetailResult> {
  ensureCallRuntime(recordId, runtime);
  const requestKey = `${runtime.apiToken}:${recordId}`;
  const existingRequest = callDetailInFlightByKey.get(requestKey);
  if (existingRequest) {
    return existingRequest;
  }

  const request = fetchCallDetail(recordId, runtime).finally(() => {
    callDetailInFlightByKey.delete(requestKey);
  });
  callDetailInFlightByKey.set(requestKey, request);
  return request;
}

async function fetchCallDetail(recordId: string, runtime: ContextRuntime): Promise<CallDetailResult> {
  const params = new URLSearchParams({
    record_id: recordId,
    _: String(Date.now()),
  });
  const response = await fetch(`/api/call?${params.toString()}`, {
    headers: {
      Accept: 'application/json',
      'X-Codex-Usage-Token': runtime.apiToken,
    },
    cache: 'no-store',
  });
  const payload = (await readJsonResponse(response, 'Call detail')) as CallDetailPayload;

  if (!payload.record?.record_id) {
    throw new Error('Call detail response did not include the requested aggregate record.');
  }

  const adjacentRows =
    Array.isArray(payload.adjacent_records) && payload.adjacent_records.length
      ? payload.adjacent_records
      : [payload.previous_record, payload.record, payload.next_record].filter((row): row is UsageRow => Boolean(row));

  return {
    record: usageRowToCall(payload.record, 0),
    previousRecord: payload.previous_record ? usageRowToCall(payload.previous_record, -1) : null,
    nextRecord: payload.next_record ? usageRowToCall(payload.next_record, 1) : null,
    adjacentRecords: adjacentRows.map((row, index) => usageRowToCall(row, index)),
    rawPayload: payload,
  };
}

function ensureCallRuntime(recordId: string, runtime: ContextRuntime) {
  if (!recordId) {
    throw new Error('record_id is required for call detail loading.');
  }
  if (runtime.fileMode) {
    throw new Error('Call detail hydration requires the localhost dashboard server.');
  }
  if (!runtime.apiToken) {
    throw new Error('Call detail hydration requires a localhost dashboard API token.');
  }
}

async function readJsonResponse(response: Response, label: string): Promise<Record<string, unknown>> {
  let payload: Record<string, unknown> = {};
  try {
    payload = (await response.json()) as Record<string, unknown>;
  } catch {
    payload = {};
  }
  if (!response.ok) {
    const message = typeof payload.error === 'string' ? payload.error : `${label} request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}
