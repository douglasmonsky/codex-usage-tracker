const prohibitedContentKeys = new Set([
  'command_text',
  'content_fragment',
  'content_fragments',
  'excerpt',
  'indexed_content',
  'indexed_fragment',
  'indexed_fragments',
  'prompt',
  'raw_context',
  'raw_output',
  'snippet',
  'tool_output',
]);

const prohibitedTrueMarkers = new Set([
  'includes_indexed_content',
  'includes_raw_fragment',
  'includes_raw_fragments',
  'indexed_content_included',
  'raw_content_included',
  'raw_context_included',
]);

const prohibitedSchemas = new Set([
  'codex-usage-tracker-context-v1',
]);

export function isBrowserCacheSafe(value: unknown): boolean {
  return inspectValue(value, new WeakSet<object>());
}

function inspectValue(value: unknown, seen: WeakSet<object>): boolean {
  if (!value || typeof value !== 'object') return true;
  if (seen.has(value)) return false;
  seen.add(value);
  const safe = Array.isArray(value) ? value.every(item => inspectValue(item, seen)) : Object.entries(value).every(([key, child]) => {
    const normalizedKey = key.toLowerCase();
    if (prohibitedContentKeys.has(normalizedKey)) return false;
    if (prohibitedTrueMarkers.has(normalizedKey) && child === true) return false;
    if (normalizedKey === 'schema' && typeof child === 'string' && prohibitedSchemas.has(child)) return false;
    return inspectValue(child, seen);
  });
  seen.delete(value);
  return safe;
}
