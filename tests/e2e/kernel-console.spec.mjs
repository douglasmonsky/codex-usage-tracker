import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("kernel-live-enabled", "false"));
});

test("warm reopen renders committed facts without starting refresh", async ({ page }) => {
  let refreshCalls = 0;
  page.on("request", (request) => {
    if (request.method() === "POST" && request.url().endsWith("/refresh")) refreshCalls += 1;
  });
  const started = performance.now();
  await page.goto("/live");
  await expect(page.getByText("Generation 1 · committed")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Usage as it lands" })).toBeVisible();
  await expect(page.getByText("Total tokens", { exact: true })).toBeVisible();
  await expect(page.getByText("Gen 1", { exact: true })).toBeVisible();
  expect(performance.now() - started).toBeLessThan(1000);

  await page.reload();
  await expect(page.getByText("Generation 1 · committed")).toBeVisible();
  expect(refreshCalls).toBe(0);
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

test("explore returns bounded facts and exact evidence deep links", async ({ page }) => {
  await page.goto("/explore");
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
  await expect(page.getByText(/Generation 1 · thread:/)).toBeVisible();
  expect(page.url()).toContain("/evidence/thread%3A");
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
  const headers = await page.locator("thead th").allTextContents();
  const callIndex = headers.indexOf("call");
  expect(callIndex).toBeGreaterThanOrEqual(0);
  const rows = page.locator("tbody tr");
  expect(await rows.count()).toBeGreaterThan(1);
  for (let index = 0; index < await rows.count(); index += 1) {
    const row = rows.nth(index);
    const call = await row.locator("td").nth(callIndex).innerText();
    const href = await row.getByRole("link", { name: "Open" }).getAttribute("href");
    expect(decodeURIComponent(href)).toContain(`/evidence/call:${call}`);
  }
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
  await expect(page.getByRole("heading", { name: "Measurement coverage" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Observed windows and local intervals" })).toBeVisible();
  await expect(page.getByText(/outside usage possible/).first()).toBeVisible();
});
