export const CONSOLE_AREAS = Object.freeze(["live", "explore", "evidence", "limits", "settings"]);

/** @param {string} pathname */
export function routeFromPath(pathname) {
  const parts = pathname.split("/").filter(Boolean);
  const area = CONSOLE_AREAS.includes(parts[0]) ? parts[0] : "live";
  const selector = area === "evidence" && parts[1]
    ? decodeURIComponent(parts.slice(1).join("/"))
    : "";
  return { area, selector };
}

/** @param {string} value */
export function commaSeparated(value) {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

/** @param {{publication_id?: string, generation: number}} payload */
export function publicationKey(payload) {
  return payload.publication_id || `generation:${payload.generation}`;
}

/** @param {number} value @param {number} maximum */
export function boundedPercent(value, maximum) {
  if (maximum <= 0) return 2;
  return Math.max(2, Math.min(100, Number(value) / maximum * 100));
}

/** @param {Record<string, unknown>} row */
export function evidenceSelectorForRow(row) {
  const candidates = [
    ["allowance", "allowance"],
    ["tool", "tool_call"],
    ["call", "call"],
    ["turn", "turn"],
    ["thread", "thread"],
  ];
  for (const [kind, field] of candidates) {
    const value = row[field];
    if (typeof value === "string" && value) return `${kind}:${value}`;
  }
  return null;
}

/** @param {unknown} cached @param {unknown} uncached */
export function cacheReuse(cached, uncached) {
  if (typeof cached !== "number" || typeof uncached !== "number") return null;
  const denominator = cached + uncached;
  return denominator > 0 ? cached / denominator : null;
}
