import assert from "node:assert/strict";
import test from "node:test";

import {
  allowancePresentation,
  boundedPercent,
  cacheReuse,
  commaSeparated,
  evidenceSelectorForRow,
  humanColumnLabel,
  materializeTemplate,
  orderedColumns,
  pageRows,
  publicationKey,
  routeFromPath,
  sortRows,
} from "../../frontend/kernel-console/model.js";

test("only approved console routes resolve", () => {
  assert.deepEqual(routeFromPath("/live"), { area: "live", selector: "" });
  assert.deepEqual(routeFromPath("/insights"), { area: "live", selector: "" });
  assert.deepEqual(routeFromPath("/evidence/thread%3Asynthetic"), {
    area: "evidence",
    selector: "thread:synthetic",
  });
});

test("query fields are normalized without inventing defaults", () => {
  assert.deepEqual(commaSeparated(" calls, total_tokens, "), ["calls", "total_tokens"]);
  assert.deepEqual(commaSeparated(""), []);
});

test("guided templates become typed requests only after parameters resolve", () => {
  const template = {
    requests: [{
      dataset: "calls",
      operation: "comparison",
      comparison: {
        current_start: "$current_start",
        current_end: "$current_end",
      },
    }],
  };

  assert.deepEqual(
    materializeTemplate(template, {
      current_start: "2026-01-08T00:00:00Z",
      current_end: "2026-01-15T00:00:00Z",
    }),
    [{
      dataset: "calls",
      operation: "comparison",
      comparison: {
        current_start: "2026-01-08T00:00:00Z",
        current_end: "2026-01-15T00:00:00Z",
      },
    }],
  );
  assert.throws(
    () => materializeTemplate(template, {}),
    /current_start/,
  );
  assert.equal(template.requests[0].comparison.current_start, "$current_start");
});

test("live publication identity is stable and percentages are bounded", () => {
  assert.equal(publicationKey({ publication_id: "sha256:abc", generation: 4 }), "sha256:abc");
  assert.equal(publicationKey({ generation: 4 }), "generation:4");
  assert.equal(boundedPercent(0, 100), 2);
  assert.equal(boundedPercent(200, 100), 100);
});

test("evidence selectors are derived from the same result row", () => {
  assert.equal(
    evidenceSelectorForRow({ thread: "thread-a", call: "call-a" }),
    "call:call-a",
  );
  assert.equal(
    evidenceSelectorForRow({ tool: "shell", tool_call: "tool-a" }),
    "tool:tool-a",
  );
  assert.equal(evidenceSelectorForRow({ model: "gpt-synthetic" }), null);
});

test("cache reuse distinguishes zero reuse from absent input", () => {
  assert.equal(cacheReuse(0, 100), 0);
  assert.equal(cacheReuse(50, 50), 0.5);
  assert.equal(cacheReuse(0, 0), null);
  assert.equal(cacheReuse(undefined, 100), null);
});

test("allowance presentation keeps exact facts, estimates, and caveats distinct", () => {
  const rows = allowancePresentation([{
    allowance_observation_id: "allowance-a",
    window_kind: "five_hour",
    observed_at: "2026-01-01T02:00:00Z",
    resets_at: 1767243600,
    used_percent: 14,
    remaining_percent: 86,
    delta_used_percent: 4,
    percentage_points_per_hour: 2,
    local_usage: { total_tokens: 400, calls: 4, turns: 2 },
    local_tokens_per_percentage_point: 100,
    local_calls_per_percentage_point: 1,
    local_turns_per_percentage_point: 0.5,
    estimated_cost_usd: 0.01,
    estimated_credits: 0.02,
    pricing_coverage: { coverage_percent: 75 },
    grade: "deterministic",
    limitations: ["outside_usage_possible"],
  }]);

  assert.deepEqual(rows, [{
    observed_at: "2026-01-01T02:00:00Z",
    resets_at: 1767243600,
    window: "five_hour",
    observed_drain_percent: 4,
    local_total_tokens: 400,
    estimated_credits: 0.02,
    estimated_credits_per_percentage_point: 0.005,
    local_tokens_per_percentage_point: 100,
    allowance_observation_id: "allowance-a",
    used_percent: 14,
    remaining_percent: 86,
    percentage_points_per_hour: 2,
    local_calls: 4,
    local_turns: 2,
    local_calls_per_percentage_point: 1,
    local_turns_per_percentage_point: 0.5,
    estimated_cost_usd: 0.01,
    pricing_coverage_percent: 75,
    grade: "deterministic",
    caveats: "outside_usage_possible",
  }]);
  assert.equal(evidenceSelectorForRow(rows[0]), "allowance:allowance-a");
  assert.equal(
    allowancePresentation([{
      delta_used_percent: 2,
      estimated_credits: null,
      local_usage: {},
      pricing_coverage: {},
      limitations: [],
    }])[0].estimated_credits_per_percentage_point,
    null,
  );
});

test("human tables put decision fields first and technical identity last", () => {
  assert.deepEqual(
    orderedColumns([
      "generation",
      "selector",
      "reasoning_tokens",
      "thread",
      "total_tokens",
      "event_at",
      "thread_label",
      "calls",
    ]),
    [
      "event_at",
      "thread_label",
      "calls",
      "total_tokens",
      "reasoning_tokens",
      "thread",
      "selector",
      "generation",
    ],
  );
  assert.equal(humanColumnLabel("thread_label"), "Thread");
  assert.equal(humanColumnLabel("configured_cost_usd"), "Cost (USD)");
  assert.equal(humanColumnLabel("estimated_credits"), "Est. credits");
  assert.equal(humanColumnLabel("adjacent_total_tokens"), "Adjacent tokens");
  assert.equal(humanColumnLabel("share_total_tokens"), "Token share");
  assert.equal(humanColumnLabel("token_mix"), "Token mix");
});

test("table sorting and pagination are deterministic without mutating facts", () => {
  const rows = [
    { thread_label: "Beta", total_tokens: 20 },
    { thread_label: "Alpha", total_tokens: 10 },
    { thread_label: "Gamma", total_tokens: null },
  ];
  assert.deepEqual(
    sortRows(rows, "thread_label", "ascending").map((row) => row.thread_label),
    ["Alpha", "Beta", "Gamma"],
  );
  assert.deepEqual(
    sortRows(rows, "total_tokens", "descending").map((row) => row.thread_label),
    ["Beta", "Alpha", "Gamma"],
  );
  assert.deepEqual(pageRows(rows, 2, 2), {
    rows: [rows[2]],
    page: 2,
    pageCount: 2,
    start: 3,
    end: 3,
  });
  assert.deepEqual(rows.map((row) => row.thread_label), ["Beta", "Alpha", "Gamma"]);
});
