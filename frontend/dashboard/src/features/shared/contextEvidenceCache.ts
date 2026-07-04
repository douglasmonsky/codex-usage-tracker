import type { ContextRequestOptions } from '../../api/context';
import type { CallContextEntry, CallContextPayload } from '../../api/types';

const contextEvidenceCache = new Map<string, CallContextPayload>();
const contextOptionMemory = new Map<string, ContextRequestOptions>();
const contextEntryOpenMemory = new Map<string, Set<string>>();
const contextEntryScrollMemory = new Map<string, Map<string, number>>();
const contextEntryShowAllMemory = new Map<string, boolean>();

export function cachedCallContext(
  recordId: string,
  options: ContextRequestOptions,
): CallContextPayload | null {
  return contextEvidenceCache.get(contextCacheKey(recordId, options)) ?? null;
}

export function rememberCallContext(
  recordId: string,
  options: ContextRequestOptions,
  payload: CallContextPayload,
) {
  contextEvidenceCache.set(contextCacheKey(recordId, options), payload);
}

export function cachedContextOptions(recordId: string): ContextRequestOptions | null {
  const options = contextOptionMemory.get(recordId);
  return options ? { ...options } : null;
}

export function rememberContextOptions(recordId: string, options: ContextRequestOptions) {
  contextOptionMemory.set(recordId, { ...options });
}

export function contextEntryKey(entry: CallContextEntry, index: number): string {
  return `${entry.type ?? 'entry'}-${entry.line_number ?? entry.timestamp ?? index}`;
}

export function cachedContextEntryOpenKeys(
  recordId: string,
  entries: CallContextEntry[],
): Set<string> {
  const remembered = contextEntryOpenMemory.get(recordId);
  if (remembered) return new Set(remembered);
  return entries.length ? new Set([contextEntryKey(entries[0], 0)]) : new Set();
}

export function rememberContextEntryOpen(recordId: string, key: string, open: boolean) {
  const current = contextEntryOpenMemory.get(recordId) ?? new Set<string>();
  if (open) {
    current.add(key);
  } else {
    current.delete(key);
  }
  contextEntryOpenMemory.set(recordId, current);
}

export function cachedContextEntryScrollTop(recordId: string, key: string): number {
  return contextEntryScrollMemory.get(recordId)?.get(key) ?? 0;
}

export function rememberContextEntryScrollTop(
  recordId: string,
  key: string,
  scrollTop: number,
) {
  const current = contextEntryScrollMemory.get(recordId) ?? new Map<string, number>();
  if (scrollTop > 0) {
    current.set(key, scrollTop);
  } else {
    current.delete(key);
  }
  contextEntryScrollMemory.set(recordId, current);
}

export function cachedContextEntryShowAll(recordId: string): boolean {
  return contextEntryShowAllMemory.get(recordId) ?? false;
}

export function rememberContextEntryShowAll(recordId: string, showAll: boolean) {
  contextEntryShowAllMemory.set(recordId, showAll);
}

export function clearContextEvidenceCache() {
  contextEvidenceCache.clear();
  contextOptionMemory.clear();
  contextEntryOpenMemory.clear();
  contextEntryScrollMemory.clear();
  contextEntryShowAllMemory.clear();
}

function contextCacheKey(recordId: string, options: ContextRequestOptions): string {
  return [
    recordId,
    options.mode,
    options.includeToolOutput ? 'tool-output' : 'no-tool-output',
    options.includeCompactionHistory ? 'compaction-history' : 'no-compaction-history',
    String(options.maxChars),
    String(options.maxEntries),
  ].join('|');
}
