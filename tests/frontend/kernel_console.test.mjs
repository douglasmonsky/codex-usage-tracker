import assert from "node:assert/strict";
import test from "node:test";

import {
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
