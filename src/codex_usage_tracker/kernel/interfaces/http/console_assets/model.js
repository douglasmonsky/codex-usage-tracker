export const CONSOLE_AREAS = Object.freeze(["live", "explore", "evidence", "limits", "settings"]);

export function materializeTemplate(template, parameters = {}) {
  if (!template || !Array.isArray(template.requests)) {
    throw new Error("Query template has no requests.");
  }
  const resolve = (value) => {
    if (typeof value === "string" && value.startsWith("$")) {
      const name = value.slice(1);
      if (!parameters[name]) {
        throw new Error(`Template parameter ${name} is required.`);
      }
      return parameters[name];
    }
    if (Array.isArray(value)) return value.map(resolve);
    if (value && typeof value === "object") {
      return Object.fromEntries(
        Object.entries(value).map(([key, item]) => [key, resolve(item)]),
      );
    }
    return value;
  };
  return resolve(template.requests);
}

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
    ["allowance", "allowance_observation_id"],
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

/** @param {Array<Record<string, unknown>>} rows */
export function allowancePresentation(rows) {
  return rows.map((row) => {
    const local = /** @type {Record<string, unknown>} */ ((
      row.local_usage && typeof row.local_usage === "object"
      ? row.local_usage
      : {}
    ));
    const pricing = /** @type {Record<string, unknown>} */ ((
      row.pricing_coverage && typeof row.pricing_coverage === "object"
      ? row.pricing_coverage
      : {}
    ));
    const limitations = Array.isArray(row.limitations) ? row.limitations : [];
    return {
      allowance_observation_id: row.allowance_observation_id,
      window: row.window_kind,
      observed_at: row.observed_at,
      used_percent: row.used_percent,
      remaining_percent: row.remaining_percent,
      delta_used_percent: row.delta_used_percent,
      percentage_points_per_hour: row.percentage_points_per_hour,
      local_total_tokens: local.total_tokens,
      local_calls: local.calls,
      local_turns: local.turns,
      local_tokens_per_percentage_point: row.local_tokens_per_percentage_point,
      local_calls_per_percentage_point: row.local_calls_per_percentage_point,
      local_turns_per_percentage_point: row.local_turns_per_percentage_point,
      estimated_cost_usd: row.estimated_cost_usd,
      estimated_credits: row.estimated_credits,
      pricing_coverage_percent: pricing.coverage_percent,
      grade: row.grade,
      caveats: limitations.join(", "),
    };
  });
}

/** @param {unknown} cached @param {unknown} uncached */
export function cacheReuse(cached, uncached) {
  if (typeof cached !== "number" || typeof uncached !== "number") return null;
  const denominator = cached + uncached;
  return denominator > 0 ? cached / denominator : null;
}
