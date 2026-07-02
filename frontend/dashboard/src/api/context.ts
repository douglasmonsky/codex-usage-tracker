import type { CallContextPayload, ContextRuntime } from './types';

export type ContextRequestOptions = {
  includeToolOutput: boolean;
  includeCompactionHistory: boolean;
  maxChars: number;
  maxEntries: number;
  mode: 'quick' | 'full';
};

export async function enableContextApi(runtime: ContextRuntime): Promise<boolean> {
  ensureContextRuntime(runtime);
  const params = new URLSearchParams({
    enabled: '1',
    _: String(Date.now()),
  });
  const response = await fetch(`/api/context-settings?${params.toString()}`, {
    headers: contextHeaders(runtime),
    cache: 'no-store',
  });
  const payload = await readJsonResponse(response, 'Context settings');
  return Boolean(payload.context_api_enabled);
}

export async function loadCallContext(
  recordId: string,
  runtime: ContextRuntime,
  options: ContextRequestOptions,
): Promise<CallContextPayload> {
  ensureContextRuntime(runtime);
  if (!runtime.contextApiEnabled) {
    throw new Error('Context API is not enabled.');
  }
  const params = new URLSearchParams({
    record_id: recordId,
    mode: options.mode,
    include_tool_output: options.includeToolOutput ? '1' : '0',
    include_compaction_history: options.includeCompactionHistory ? '1' : '0',
    max_chars: String(options.maxChars),
    max_entries: String(options.maxEntries),
    _: String(Date.now()),
  });
  const payload = await fetch(`/api/context?${params.toString()}`, {
    headers: contextHeaders(runtime),
    cache: 'no-store',
  }).then(response => readJsonResponse(response, 'Context'));
  return payload as CallContextPayload;
}

function ensureContextRuntime(runtime: ContextRuntime) {
  if (runtime.fileMode) {
    throw new Error('Context loading requires the localhost dashboard server.');
  }
  if (!runtime.apiToken) {
    throw new Error('Context loading requires a localhost dashboard API token.');
  }
}

function contextHeaders(runtime: ContextRuntime): HeadersInit {
  return {
    Accept: 'application/json',
    'X-Codex-Usage-Token': runtime.apiToken,
  };
}

async function readJsonResponse(response: Response, label: string): Promise<Record<string, unknown>> {
  let payload: Record<string, unknown> = {};
  try {
    payload = (await response.json()) as Record<string, unknown>;
  } catch {
    payload = {};
  }
  if (!response.ok) {
    const message = typeof payload.error === 'string' ? payload.error : `${label} API returned HTTP ${response.status}.`;
    throw new Error(message);
  }
  if (typeof payload.error === 'string') {
    throw new Error(payload.error);
  }
  return payload;
}
