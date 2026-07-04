import type { ContextRequestOptions } from '../../api/context';
import type { CallContextPayload, ContextRuntime } from '../../api/types';
import { formatNumber } from './format';

export type ContextLoadState =
  | { status: 'idle'; message?: string }
  | { status: 'loading'; message: string }
  | { status: 'loaded'; payload: CallContextPayload }
  | { status: 'error'; message: string };

export const defaultContextOptions: ContextRequestOptions = {
  includeToolOutput: false,
  includeCompactionHistory: false,
  maxChars: 8_000,
  maxEntries: 20,
  mode: 'quick',
};

export function contextOptionsFromSearch(
  search = window.location.search,
  fallback: ContextRequestOptions = defaultContextOptions,
): ContextRequestOptions {
  const params = new URLSearchParams(search);
  return {
    includeToolOutput: boolParam(params.get('include_tool_output'), fallback.includeToolOutput),
    includeCompactionHistory: boolParam(params.get('include_compaction_history'), fallback.includeCompactionHistory),
    maxChars: nonNegativeIntParam(params.get('max_chars'), fallback.maxChars),
    maxEntries: nonNegativeIntParam(params.get('max_entries'), fallback.maxEntries),
    mode: params.get('mode') === 'full' ? 'full' : fallback.mode,
  };
}

export function applyContextOptionsToUrl(
  url: URL,
  options: ContextRequestOptions,
  defaults: ContextRequestOptions = defaultContextOptions,
): void {
  setOptionalContextParam(url, 'mode', options.mode, defaults.mode);
  setOptionalContextParam(url, 'max_entries', String(options.maxEntries), String(defaults.maxEntries));
  setOptionalContextParam(url, 'max_chars', String(options.maxChars), String(defaults.maxChars));
  setOptionalContextParam(url, 'include_tool_output', options.includeToolOutput ? '1' : '0', defaults.includeToolOutput ? '1' : '0');
  setOptionalContextParam(
    url,
    'include_compaction_history',
    options.includeCompactionHistory ? '1' : '0',
    defaults.includeCompactionHistory ? '1' : '0',
  );
}

export function contextRuntimeMessage(runtime: ContextRuntime): string {
  if (runtime.fileMode) {
    return 'Static file mode cannot read local JSONL context. Use serve-dashboard with the context API enabled.';
  }
  if (!runtime.apiToken) {
    return 'Context loading requires the localhost dashboard server API token.';
  }
  if (!runtime.contextApiEnabled) {
    return 'Context API is available but off. Enable it here before loading selected-turn evidence.';
  }
  return 'Context API is enabled. Load selected-turn evidence from the local JSONL source only when needed.';
}

function boolParam(value: string | null, fallback: boolean): boolean {
  if (value === '1' || value === 'true') return true;
  if (value === '0' || value === 'false') return false;
  return fallback;
}

function nonNegativeIntParam(value: string | null, fallback: number): number {
  if (value === null || value.trim() === '') return fallback;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? Math.floor(parsed) : fallback;
}

function setOptionalContextParam(url: URL, name: string, value: string, defaultValue: string): void {
  if (value === defaultValue) {
    url.searchParams.delete(name);
  } else {
    url.searchParams.set(name, value);
  }
}

export function contextErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export function olderContextOptions(
  payload: CallContextPayload,
  options: ContextRequestOptions,
): ContextRequestOptions {
  const currentMaxEntries = Number(payload.omitted?.max_entries ?? options.maxEntries ?? defaultContextOptions.maxEntries);
  const baseIncrement = defaultContextOptions.maxEntries || 20;
  const nextMaxEntries = currentMaxEntries > 0 ? Math.max(currentMaxEntries + baseIncrement, currentMaxEntries * 2) : 0;
  return { ...options, maxEntries: nextMaxEntries };
}

export function contextEvidenceNotes(payload: CallContextPayload): string[] {
  const omitted = payload.omitted ?? {};
  const source = payload.source ?? {};
  const notes = [
    'Local JSONL context loaded on demand.',
    payload.include_tool_output
      ? 'Tool output included with redaction and size limits.'
      : 'Tool output hidden for this view.',
  ];
  if (source.file) {
    notes.push(`Source: ${source.file}${source.line_number ? `:${source.line_number}` : ''}.`);
  }
  const olderEntries = Number(omitted.older_entries ?? 0);
  if (olderEntries > 0) {
    notes.push(`${formatNumber(olderEntries)} older entries omitted.`);
  }
  const overBudgetChars = Number(omitted.over_budget_chars ?? 0);
  if (overBudgetChars > 0) {
    notes.push(`${formatNumber(overBudgetChars)} chars over budget omitted.`);
  }
  if (Number(omitted.max_chars ?? NaN) === 0) {
    notes.push('No character limit applied.');
  }
  return notes;
}
