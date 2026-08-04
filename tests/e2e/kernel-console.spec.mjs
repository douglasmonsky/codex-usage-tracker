import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("kernel-live-enabled", "false"));
});

test("warm reopen renders committed facts without starting refresh", async ({ page }) => {
  let refreshCalls = 0;
  let statusCalls = 0;
  let queryCalls = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/refresh")) refreshCalls += 1;
    if (request.method() === "GET" && request.url().endsWith("/status")) statusCalls += 1;
    if (request.method() === "POST" && request.url().endsWith("/query")) queryCalls += 1;
  });
  await page.goto("/live");
  await expect(page.getByText("Generation 1 · committed")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Usage as it lands" })).toBeVisible();
  await expect(page.getByText("Total tokens", { exact: true })).toBeVisible();
  await expect(page.getByText("Cost and credits", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Load detailed views" })).toBeVisible();
  const browserReadyMs = await page.evaluate(() => performance.now());
  expect(browserReadyMs).toBeLessThan(500);

  await page.reload();
  await expect(page.getByText("Generation 1 · committed")).toBeVisible();
  expect(refreshCalls).toBe(0);
  expect(statusCalls).toBe(2);
  expect(queryCalls).toBe(1);
});

test("only the five focused areas are navigable and keyboard reachable", async ({ page }) => {
  await page.goto("/live");
  const navigation = page.getByRole("navigation", { name: "Primary navigation" });
  if (await navigation.isHidden()) await page.getByRole("button", { name: "Toggle navigation" }).click();
  await expect(navigation.getByRole("link")).toHaveCount(5);
  for (const area of ["Explore", "Evidence", "Limits", "Settings", "Live"]) {
    if (await navigation.isHidden()) await page.getByRole("button", { name: "Toggle navigation" }).click();
    await navigation.getByRole("link", { name: area }).click();
    await expect(page.locator(`nav a[data-route="${area.toLowerCase()}"]`)).toHaveAttribute("aria-current", "page");
  }
  await page.reload();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to workspace" })).toBeFocused();
});

test("language selection persists in the local console", async ({ page }) => {
  await page.goto("/settings");
  await page.getByLabel("Language").selectOption("zh-CN");
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  await expect(page.locator('nav a[data-route="live"]')).toContainText("实时概览");
  await page.reload();
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
});

test("explore returns bounded facts and exact evidence deep links", async ({ page }) => {
  await page.goto("/explore");
  await expect(page.getByRole("heading", { name: "Top threads" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recent calls" })).toBeVisible();
  await page.getByLabel("Group by").fill("model");
  await page.getByRole("button", { name: "Save locally" }).click();
  await page.getByLabel("Group by").fill("thread");
  await page.getByRole("button", { name: "Load saved" }).click();
  await expect(page.getByLabel("Group by")).toHaveValue("model");
  await page.getByLabel("Group by").fill("thread");
  await page.getByRole("button", { name: "Run bounded query" }).click();
  await expect(page.getByText(/Generation 1 · \d+ of \d+ rows/)).toBeVisible();
  const evidence = page.getByRole("link", { name: "Open" }).first();
  await expect(evidence).toHaveAttribute("href", /^\/evidence\/thread%3A/);
  await evidence.click();
  await expect(page.getByText(/\d+ of \d+ evidence rows/)).toBeVisible();
  await page.getByText("Evidence identity and provenance").click();
  await expect(page.locator(".evidence-provenance dd").first()).toContainText("thread:");
  expect(page.url()).toContain("/evidence/thread%3A");
});

test("human tables sort with the keyboard and paginate without new API work", async ({ page }) => {
  let queryCalls = 0;
  await page.route("**/api/kernel/v1/query", async (route) => {
    queryCalls += 1;
    const rows = Array.from({ length: 23 }, (_, index) => ({
      thread: `thread-${String(index + 1).padStart(2, "0")}`,
      thread_label: `Project ${String.fromCharCode(65 + (22 - index))}`,
      calls: index + 1,
      uncached_input_tokens: 100 + index,
      cached_input_tokens: 200 + index,
      reasoning_tokens: 30 + index,
      output_tokens: 40 + index,
      total_tokens: 370 + (index * 4),
      configured_cost_usd: 0.0000335 * (index + 1),
      estimated_credits: 0.000082 * (index + 1),
    }));
    const coverage = {
      measures: {
        configured_cost_usd: {
          observed_count: 22,
          missing_count: 1,
          coverage_percent: 95.65,
          confidence: "configured",
          provenance: "synthetic rate card",
        },
        estimated_credits: {
          observed_count: 22,
          missing_count: 1,
          coverage_percent: 95.65,
          confidence: "estimated",
          provenance: "synthetic rate card",
        },
      },
      rate_card: { status: "ready" },
    };
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        results: [
          {
            dataset: "calls",
            operation: "aggregate",
            generation: 1,
            grade: "exact",
            matched_count: 23,
            returned_count: 1,
            elapsed_ms: 1,
            coverage,
            rows: [rows.reduce((total, row) => ({
              calls: total.calls + row.calls,
              uncached_input_tokens: total.uncached_input_tokens + row.uncached_input_tokens,
              cached_input_tokens: total.cached_input_tokens + row.cached_input_tokens,
              reasoning_tokens: total.reasoning_tokens + row.reasoning_tokens,
              output_tokens: total.output_tokens + row.output_tokens,
              total_tokens: total.total_tokens + row.total_tokens,
              configured_cost_usd: total.configured_cost_usd + row.configured_cost_usd,
              estimated_credits: total.estimated_credits + row.estimated_credits,
            }), {
              calls: 0,
              uncached_input_tokens: 0,
              cached_input_tokens: 0,
              reasoning_tokens: 0,
              output_tokens: 0,
              total_tokens: 0,
              configured_cost_usd: 0,
              estimated_credits: 0,
            })],
          },
          {
            dataset: "calls",
            operation: "share",
            generation: 1,
            grade: "exact",
            matched_count: 23,
            returned_count: 23,
            elapsed_ms: 1,
            coverage,
            rows,
          },
          {
            dataset: "calls",
            operation: "time_series",
            generation: 1,
            grade: "exact",
            matched_count: 1,
            returned_count: 1,
            elapsed_ms: 1,
            coverage,
            rows: [{
              time_day: "2026-01-01",
              uncached_input_tokens: 100,
              cached_input_tokens: 200,
              reasoning_tokens: 30,
              output_tokens: 40,
              total_tokens: 370,
              configured_cost_usd: 0.01,
              estimated_credits: 0.02,
            }],
          },
        ],
      }),
    });
  });
  await page.goto("/live");
  await page.getByRole("button", { name: "Load detailed views" }).click();
  const leaders = page.getByRole("heading", { name: "Highest-token threads" })
    .locator("..");
  await expect(page.getByText("$0.0000335", { exact: true })).toBeVisible();
  await expect(page.getByText("0.000082 credits", { exact: true })).toBeVisible();
  await expect(page.getByText(/cost 95.7% rated · 1 missing/).first()).toBeVisible();
  await expect(page.getByText(/rate card ready/).first()).toBeVisible();
  const tokenHeader = leaders.getByRole("columnheader", { name: "Total tokens" });
  const tokenSort = leaders.getByRole("button", { name: "Total tokens" });
  await tokenSort.focus();
  await page.keyboard.press("Enter");
  await expect(tokenHeader).toHaveAttribute("aria-sort", "descending");
  await expect(tokenSort).not.toHaveAttribute("aria-sort", /.*/);
  const filter = leaders.getByLabel("Filter Highest-token threads rows");
  await filter.fill("Project A");
  await expect(leaders.getByText("Rows 1–1 of 1")).toBeVisible();
  await filter.fill("");
  await leaders.getByRole("button", { name: "Next page" }).click();
  await expect(leaders.getByText("Rows 11–20 of 23")).toBeVisible();
  expect(queryCalls).toBe(2);
});

test("every guided query template submits an allowlisted request", async ({ page }) => {
  await page.goto("/explore");
  for (const template of [
    "allowance",
    "concentration",
    "model_effort",
    "period_comparison",
    "subagents",
    "tools",
    "turns",
  ]) {
    await page.getByLabel("Guided template").selectOption(template);
    await page.getByRole("button", { name: "Run bounded query" }).click();
    await expect(
      page.locator(".query-result .result-meta").first(),
    ).toContainText(/Generation 1 · \d+ of \d+ rows/);
    await expect(page.getByText("This view could not load")).toHaveCount(0);
  }
});

test("non-comparison templates ignore blank comparison controls", async ({ page }) => {
  await page.goto("/explore");
  await page.getByLabel("Previous start").fill("");
  await page.getByLabel("Current end").fill("");
  await page.getByLabel("Guided template").selectOption("tools");
  await page.getByRole("button", { name: "Run bounded query" }).click();
  await expect(
    page.locator(".query-result .result-meta").first(),
  ).toContainText(/Generation 1 · \d+ of \d+ rows/);
  await expect(page.getByText("This view could not load")).toHaveCount(0);
});

test("Explore switches between curated Calls and Threads requests", async ({ page }) => {
  await page.goto("/explore");
  await page.getByLabel("Dataset").selectOption("threads");
  await expect(page.getByLabel("Group by")).toHaveValue("project");
  await page.getByRole("button", { name: "Run bounded query" }).click();
  await expect(page.getByRole("heading", { name: "threads · aggregate" })).toBeVisible();
  await expect(page.locator(".query-result tbody tr")).not.toHaveCount(0);

  await page.getByLabel("Dataset").selectOption("calls");
  await expect(page.getByLabel("Group by")).toHaveValue("thread");
  await page.getByRole("button", { name: "Run bounded query" }).click();
  await expect(page.getByRole("heading", { name: "calls · share" })).toBeVisible();
  await expect(page.locator(".query-result tbody tr")).not.toHaveCount(0);
});

test("clipboard denial is reported without an unhandled action", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: () => Promise.reject(new Error("synthetic denial")),
      },
    });
  });
  await page.goto("/explore");
  await page.getByRole("button", { name: "Copy typed request" }).click();
  await expect(page.getByText(
    "Unable to copy typed request: synthetic denial",
  )).toBeVisible();
});

test("each result row links to its own most-specific evidence", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "one exact row mapping is sufficient");
  await page.goto("/explore");
  await page.getByLabel("Operation").selectOption("rows");
  await page.getByLabel("Group by").fill("call,thread");
  await page.getByLabel("Measures").fill("total_tokens");
  await page.getByRole("button", { name: "Run bounded query" }).click();
  const result = page.locator(".query-result").first();
  await expect(result.getByRole("heading", { name: "calls · rows" })).toBeVisible();
  await expect(result.getByRole("columnheader", { name: "call" })).toHaveCount(0);
  const rows = result.locator("tbody tr");
  expect(await rows.count()).toBeGreaterThan(1);
  for (let index = 0; index < await rows.count(); index += 1) {
    const row = rows.nth(index);
    const href = await row.getByRole("link", { name: "Open" }).getAttribute("href");
    const selector = decodeURIComponent(href).match(/\/evidence\/(call:[^?]+)/)?.[1];
    expect(selector).toBeTruthy();
    await row.getByText("Technical").click();
    await expect(row.locator("code")).toContainText(selector.slice(5));
  }
});

test("evidence cost enrichment fails closed across generations", async ({ page }) => {
  await page.route("**/api/kernel/v1/evidence", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        generation: 1,
        selector: "call:call-a",
        grade: "exact",
        matched_count: 1,
        returned_count: 1,
        rows: [{
          event_at: "2026-01-01T00:00:00Z",
          event_kind: "model_call",
          selector: "call:call-a",
        }],
      }),
    });
  });
  await page.route("**/api/kernel/v1/query", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        results: [{
          generation: 2,
          rows: [{
            call: "call-a",
            configured_cost_usd: 0.0000335,
            estimated_credits: 0.000082,
          }],
        }],
      }),
    });
  });
  await page.goto("/evidence/call%3Acall-a?view=timeline");
  await expect(page.getByText(
    /newer committed generation arrived while evidence was loading/i,
  )).toBeVisible();
});

test("explicit refresh sends one request and uses one host-held job wait", async ({ page }) => {
  let refreshCalls = 0;
  let jobCalls = 0;
  await page.route("**/api/kernel/v1/refresh", async (route) => {
    refreshCalls += 1;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        disposition: "started",
        job: { job_id: "synthetic-job" },
      }),
    });
  });
  await page.route("**/api/kernel/v1/jobs/synthetic-job**", async (route) => {
    jobCalls += 1;
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        terminal: true,
        state: "completed",
        stage: "complete",
        output_generation: 1,
      }),
    });
  });
  await page.goto("/live");
  await page.getByRole("button", { name: "Refresh data" }).click();
  await expect.poll(() => refreshCalls).toBe(1);
  await expect.poll(() => jobCalls).toBe(1);
});

test("stale or active-refresh status never replaces committed totals with zero", async ({ page }) => {
  await page.route("**/api/kernel/v1/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        version: "0.26.0",
        state: "stale",
        generation: 1,
        publication_id: "sha256:synthetic",
        refresh: {
          stage: "parsing",
          progress_percent: 42,
        },
      }),
    });
  });
  await page.goto("/live");
  await expect(page.getByText("Generation 1 · committed")).toBeVisible();
  await expect(page.locator("#freshness-chip")).toHaveText("Refresh 42%");
  await expect(page.getByText("Total tokens", { exact: true })).toBeVisible();
  await expect(page.getByText("0", { exact: true })).toHaveCount(0);
});

test("stale snapshot is explicit while committed facts remain visible", async ({ page }) => {
  await page.route("**/api/kernel/v1/status", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        version: "0.26.0",
        state: "stale",
        generation: 1,
        publication_id: "sha256:synthetic",
        refresh: null,
      }),
    });
  });
  await page.goto("/live");
  await expect(page.locator("#freshness-chip")).toHaveText("Stale snapshot");
  await expect(page.getByText("Generation 1 · committed")).toBeVisible();
  await expect(page.getByText("515", { exact: true })).toBeVisible();
});

test("live replay and reconnect do not reannounce the committed generation", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "one real reconnect is sufficient");
  let eventRequests = 0;
  page.on("request", (request) => {
    if (request.url().includes("/api/kernel/v1/events")) eventRequests += 1;
  });
  await page.goto("/settings");
  await page.getByLabel("Watch for committed generations").check();
  await expect.poll(() => eventRequests, { timeout: 7_000 }).toBeGreaterThanOrEqual(2);
  await expect(page.locator("#toast-region .toast")).toHaveCount(0);
});

test("snapshot gap resnapshots before reopening without the stale event cursor", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "one browser contract check is sufficient");
  await page.goto("/settings");
  await page.evaluate(() => {
    window.__syntheticEventSources = [];
    window.EventSource = class SyntheticEventSource {
      constructor(url) {
        this.url = url;
        this.closed = false;
        this.listeners = new Map();
        window.__syntheticEventSources.push(this);
      }

      addEventListener(kind, listener) {
        this.listeners.set(kind, listener);
      }

      close() {
        this.closed = true;
      }
    };
  });
  await page.getByLabel("Watch for committed generations").check();
  await expect.poll(
    () => page.evaluate(() => window.__syntheticEventSources.length),
  ).toBe(1);

  await page.evaluate(() => {
    const first = window.__syntheticEventSources[0];
    first.listeners.get("snapshot_required")();
  });

  await expect.poll(
    () => page.evaluate(() => window.__syntheticEventSources.length),
  ).toBe(2);
  const state = await page.evaluate(() => ({
    firstClosed: window.__syntheticEventSources[0].closed,
    secondUrl: window.__syntheticEventSources[1].url,
  }));
  expect(state).toEqual({
    firstClosed: true,
    secondUrl: "/api/kernel/v1/events?limit=100",
  });

  await page.evaluate(() => {
    const second = window.__syntheticEventSources[1];
    second.listeners.get("snapshot_required")();
  });
  await expect.poll(
    () => page.evaluate(() => window.__syntheticEventSources.length),
  ).toBe(2);
});

test("error recovery control retries the failed view", async ({ page }) => {
  let failures = 0;
  await page.route("**/api/kernel/v1/query", async (route) => {
    if (failures === 0) {
      failures += 1;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: "synthetic temporary failure" }),
      });
    } else {
      await route.continue();
    }
  });
  await page.goto("/live");
  await expect(page.getByText("synthetic temporary failure")).toBeVisible();
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.getByText("515", { exact: true })).toBeVisible();
});

test("limits preserve fact grade and caveat language", async ({ page }) => {
  await page.goto("/limits");
  await expect(page.getByRole("heading", { name: "Capacity and limits" })).toBeVisible();
  await expect(page.getByText(/not causal billing attribution/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Usage over time" })).toBeVisible();
  await expect(page.getByRole("img", { name: /allowance usage over time/i })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Observed usage and local impact" })).toBeVisible();
  const firstHeader = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Observed usage and local impact" }),
  }).locator("thead th").first();
  await expect(firstHeader).toContainText("Observed");
  await expect(page.locator("tbody").getByText(/^\d{1,3}(,\d{3}){3}$/)).toHaveCount(0);
  await expect(page.getByText(/outside usage possible/).first()).toBeVisible();
});

test("limits graph uses elapsed time and labels reset boundaries", async ({ page }) => {
  await page.route("**/api/kernel/v1/allowance?limit=100", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        returned_count: 3,
        observed_through: "2026-01-11T12:00:00Z",
        coverage: { pricing: { configured: true, coverage_percent: 100 } },
        intervals: [
          {
            allowance_observation_id: "allowance-a",
            window_kind: "weekly",
            observed_at: "2026-01-01T12:00:00Z",
            resets_at: 1767571200,
            used_percent: 10,
            remaining_percent: 90,
            local_usage: {},
            pricing_coverage: {},
            limitations: [],
          },
          {
            allowance_observation_id: "allowance-b",
            window_kind: "weekly",
            observed_at: "2026-01-02T12:00:00Z",
            resets_at: 1767571200,
            used_percent: 20,
            remaining_percent: 80,
            local_usage: {},
            pricing_coverage: {},
            limitations: [],
          },
          {
            allowance_observation_id: "allowance-c",
            window_kind: "weekly",
            observed_at: "2026-01-11T12:00:00Z",
            resets_at: 1768176000,
            used_percent: 60,
            remaining_percent: 40,
            local_usage: {},
            pricing_coverage: {},
            limitations: [],
          },
        ],
      }),
    });
  });
  await page.goto("/limits");
  await expect(page.locator(".allowance-chart .chart-point")).toHaveCount(3);
  const positions = await page.locator(".allowance-chart .chart-point").evaluateAll(
    (nodes) => nodes.map((node) => Number(node.getAttribute("cx"))),
  );
  expect(positions[2] - positions[1]).toBeGreaterThan(
    5 * (positions[1] - positions[0]),
  );
  await expect(page.locator(".allowance-chart .chart-reset")).toHaveCount(1);
  await expect(page.getByText("Jan 1", { exact: true })).toBeVisible();
  await expect(page.getByText("Jan 11", { exact: true })).toBeVisible();
});

test("primary console surfaces hide implementation-first labels", async ({ page }) => {
  await page.goto("/live");
  await page.getByRole("button", { name: "Load detailed views" }).click();
  await expect(page.getByText("Snapshot truth", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Tool-independent facts", { exact: true })).toHaveCount(0);
  const leaders = page.getByRole("heading", { name: "Highest-token threads" })
    .locator("..");
  await expect(leaders.getByRole("columnheader", { name: "Token share" })).toBeVisible();
  await expect(leaders.getByRole("columnheader", { name: "thread", exact: true })).toHaveCount(0);
  await expect(leaders.getByRole("columnheader", { name: "share calls", exact: true })).toHaveCount(0);
  await leaders.getByRole("link", { name: "Open" }).first().click();
  await expect(page.getByRole("columnheader", { name: "Turn" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Event / tool" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Cost (USD)" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Est. credits" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Selector", exact: true })).toHaveCount(0);
});
