import assert from "node:assert/strict";
import test from "node:test";

import {
  allowancePresentation,
  boundedPercent,
  cacheReuse,
  commaSeparated,
  evidenceSelectorForRow,
  publicationKey,
  routeFromPath,
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
    allowance_observation_id: "allowance-a",
    window: "five_hour",
    observed_at: "2026-01-01T02:00:00Z",
    used_percent: 14,
    remaining_percent: 86,
    delta_used_percent: 4,
    percentage_points_per_hour: 2,
    local_total_tokens: 400,
    local_calls: 4,
    local_turns: 2,
    local_tokens_per_percentage_point: 100,
    local_calls_per_percentage_point: 1,
    local_turns_per_percentage_point: 0.5,
    estimated_cost_usd: 0.01,
    estimated_credits: 0.02,
    pricing_coverage_percent: 75,
    grade: "deterministic",
    caveats: "outside_usage_possible",
  }]);
  assert.equal(evidenceSelectorForRow(rows[0]), "allowance:allowance-a");
});
