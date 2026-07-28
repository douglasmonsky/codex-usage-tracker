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

const PRIMARY_COLUMN_ORDER = Object.freeze([
  "event_at",
  "observed_at",
  "resets_at",
  "time_day",
  "time_hour",
  "turn_ordinal",
  "thread_label",
  "project",
  "model",
  "effort",
  "event_kind",
  "safe_label",
  "tool",
  "operation",
  "target",
  "target_label",
  "status",
  "calls",
  "turns",
  "tools",
  "total_tokens",
  "token_mix",
  "uncached_input_tokens",
  "cached_input_tokens",
  "reasoning_tokens",
  "output_tokens",
  "adjacent_total_tokens",
  "adjacent_token_mix",
  "adjacent_uncached_input_tokens",
  "adjacent_cached_input_tokens",
  "adjacent_reasoning_tokens",
  "adjacent_output_tokens",
  "configured_cost_usd",
  "estimated_credits",
  "duration_ms",
  "output_bytes",
  "observed_drain_percent",
  "used_percent",
  "remaining_percent",
  "local_total_tokens",
  "local_tokens_per_percentage_point",
]);

const TECHNICAL_COLUMN_ORDER = Object.freeze([
  "call",
  "turn",
  "thread",
  "tool_call",
  "allowance_observation_id",
  "selector",
  "generation",
  "grade",
]);

const COLUMN_LABELS = Object.freeze({
  adjacent_cached_input_tokens: "Adjacent cached input",
  adjacent_output_tokens: "Adjacent output",
  adjacent_reasoning_tokens: "Adjacent reasoning",
  adjacent_total_tokens: "Adjacent tokens",
  adjacent_token_mix: "Adjacent token mix",
  adjacent_uncached_input_tokens: "Adjacent new input",
  configured_cost_usd: "Cost (USD)",
  estimated_credits: "Est. credits",
  estimated_credits_per_percentage_point: "Est. credits / point",
  event_at: "Time",
  event_kind: "Event / tool",
  local_total_tokens: "Total tokens",
  local_tokens_per_percentage_point: "Tokens / point",
  observed_at: "Observed",
  observed_drain_percent: "Usage drain",
  output_bytes: "Tool output bytes",
  resets_at: "Resets",
  remaining_percent: "Remaining",
  safe_label: "Name",
  share_total_tokens: "Token share",
  target_label: "Target",
  token_mix: "Token mix",
  used_percent: "Used",
  window: "Window",
  thread_label: "Thread",
  time_day: "Day",
  time_hour: "Hour",
  turn_ordinal: "Turn",
});

/** @param {string[]} columns */
export function orderedColumns(columns) {
  const rank = new Map(
    [...PRIMARY_COLUMN_ORDER, ...TECHNICAL_COLUMN_ORDER].map(
      (column, index) => [column, index],
    ),
  );
  return [...columns].sort((left, right) => {
    const leftRank = rank.get(left) ?? PRIMARY_COLUMN_ORDER.length;
    const rightRank = rank.get(right) ?? PRIMARY_COLUMN_ORDER.length;
    if (leftRank !== rightRank) return leftRank - rightRank;
    return left.localeCompare(right);
  });
}

/** @param {string} column */
export function humanColumnLabel(column) {
  return COLUMN_LABELS[column] || column.replaceAll("_", " ");
}

/**
 * @param {Array<Record<string, unknown>>} rows
 * @param {string} column
 * @param {"ascending"|"descending"} direction
 */
export function sortRows(rows, column, direction) {
  const factor = direction === "ascending" ? 1 : -1;
  return [...rows].sort((left, right) => {
    const a = left[column];
    const b = right[column];
    if (a === null || a === undefined) return b === null || b === undefined ? 0 : 1;
    if (b === null || b === undefined) return -1;
    if (typeof a === "number" && typeof b === "number") return (a - b) * factor;
    return String(a).localeCompare(String(b), undefined, {
      numeric: true,
      sensitivity: "base",
    }) * factor;
  });
}

/**
 * @param {Array<Record<string, unknown>>} rows
 * @param {number} requestedPage
 * @param {number} pageSize
 */
export function pageRows(rows, requestedPage, pageSize) {
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const page = Math.min(Math.max(1, requestedPage), pageCount);
  const offset = (page - 1) * pageSize;
  const visible = rows.slice(offset, offset + pageSize);
  return {
    rows: visible,
    page,
    pageCount,
    start: visible.length ? offset + 1 : 0,
    end: offset + visible.length,
  };
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
    const drain = Number(row.delta_used_percent);
    const hasCredits = row.estimated_credits !== null
      && row.estimated_credits !== undefined;
    const credits = Number(row.estimated_credits);
    return {
      observed_at: row.observed_at,
      resets_at: row.resets_at,
      window: row.window_kind,
      observed_drain_percent: row.delta_used_percent,
      local_total_tokens: local.total_tokens,
      estimated_credits: row.estimated_credits,
      estimated_credits_per_percentage_point: (
        Number.isFinite(drain)
        && drain > 0
        && hasCredits
        && Number.isFinite(credits)
          ? credits / drain
          : null
      ),
      local_tokens_per_percentage_point: row.local_tokens_per_percentage_point,
      allowance_observation_id: row.allowance_observation_id,
      used_percent: row.used_percent,
      remaining_percent: row.remaining_percent,
      percentage_points_per_hour: row.percentage_points_per_hour,
      local_calls: local.calls,
      local_turns: local.turns,
      local_calls_per_percentage_point: row.local_calls_per_percentage_point,
      local_turns_per_percentage_point: row.local_turns_per_percentage_point,
      estimated_cost_usd: row.estimated_cost_usd,
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
