import { expect, test } from '@playwright/test';
import { performance } from 'node:perf_hooks';

const budgetsMs = {
  startup5k: 15_000,
  uncapped5k: 15_000,
  startup100k: 60_000,
  cachedReload5k: 15_000,
  appendedRefresh5k: 15_000,
};

test.describe('dashboard release-candidate performance evidence', () => {
  test.describe.configure({ mode: 'serial', timeout: 90_000 });

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'Performance evidence uses one stable desktop browser profile.');
    page.on('pageerror', error => {
      throw error;
    });
  });

  test('starts deterministically with 5k synthetic rows inside the startup budget', async ({ page }, testInfo) => {
    await installSyntheticBoot(page, { rowCount: 5_000, limit: 5_000 });

    const elapsedMs = await openCallsAndMeasure(page);

    await expect(page.getByText('5,000 ranked evidence rows', { exact: true })).toBeVisible();
    await expectVirtualizedRowWindow(page, 5_000);
    expect(
      elapsedMs,
      `5k synthetic startup took ${formatMs(elapsedMs)}, exceeding the ${formatMs(budgetsMs.startup5k)} RC budget; inspect boot-to-model conversion and first Calls render.`,
    ).toBeLessThanOrEqual(budgetsMs.startup5k);
    await attachEvidence(testInfo, 'startup-5k', { elapsedMs, budgetMs: budgetsMs.startup5k, rows: 5_000 });
  });

  test('loads the 5k synthetic history in No cap mode inside the paging budget', async ({ page }, testInfo) => {
    const allRows = syntheticRows(5_000);
    await installSyntheticBoot(page, { rowCount: 500, limit: 500, totalRows: 5_000, apiToken: 'performance-token' });
    let usageRequests = 0;
    await page.route('**/api/usage?**', async route => {
      usageRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(syntheticPayload(allRows, { limit: 10_000, totalRows: 5_000, apiToken: 'performance-token' })),
      });
    });
    await page.goto('/?view=calls&sort=cost&qa=r11-performance-no-cap');
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();

    const startedAt = performance.now();
    await page.getByRole('button', { name: 'Load all rows', exact: true }).click();
    await expect(page.getByText('5,000 ranked evidence rows', { exact: true })).toBeVisible();
    await expect(page.getByLabel('Row limit control')).toContainText('All rows mode');
    const elapsedMs = performance.now() - startedAt;

    expect(usageRequests, 'No cap should fetch the bounded 5k synthetic history in one 10k page.').toBe(1);
    expect(
      elapsedMs,
      `No cap loading took ${formatMs(elapsedMs)}, exceeding the ${formatMs(budgetsMs.uncapped5k)} RC budget; inspect /api/usage paging and model replacement.`,
    ).toBeLessThanOrEqual(budgetsMs.uncapped5k);
    await attachEvidence(testInfo, 'no-cap-5k', { elapsedMs, budgetMs: budgetsMs.uncapped5k, rows: 5_000, usageRequests });
  });

  test('keeps a 100k synthetic history virtualized inside the focused-load budget', async ({ page }, testInfo) => {
    const focusedRows = syntheticRows(100_000);
    await installSyntheticBoot(page, { rowCount: 500, limit: 500, totalRows: 100_000, apiToken: 'performance-token' });
    await page.route('**/api/calls?**', async route => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schema: 'codex-usage-tracker-calls-v1',
          rows: focusedRows,
          row_count: focusedRows.length,
          total_matched_rows: focusedRows.length,
          limit: null,
          offset: 0,
          has_more: false,
          next_offset: null,
        }),
      });
    });

    const startedAt = performance.now();
    await page.goto('/?view=calls&qa=r11-performance-virtualized');
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible({ timeout: budgetsMs.startup100k });
    await expect(page.getByText('100,000 ranked evidence rows', { exact: true })).toBeVisible({ timeout: budgetsMs.startup100k });
    const elapsedMs = performance.now() - startedAt;
    const renderedRows = await expectVirtualizedRowWindow(page, 100_000);

    expect(
      elapsedMs,
      `100k virtualized focused load took ${formatMs(elapsedMs)}, exceeding the ${formatMs(budgetsMs.startup100k)} RC budget; inspect calls response decoding and EvidenceGrid row-model work.`,
    ).toBeLessThanOrEqual(budgetsMs.startup100k);
    await attachEvidence(testInfo, 'virtualized-100k', {
      elapsedMs,
      budgetMs: budgetsMs.startup100k,
      rows: 100_000,
      renderedRows,
    });
  });

  test('reuses the loaded 5k snapshot across reload without a usage request', async ({ page }, testInfo) => {
    await installSyntheticBoot(page, { rowCount: 5_000, limit: 5_000, apiToken: 'performance-token' });
    let usageRequests = 0;
    await page.route('**/api/usage?**', async route => {
      usageRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(syntheticPayload(syntheticRows(5_000), { limit: 5_000, apiToken: 'performance-token' })),
      });
    });
    await page.goto('/?view=calls&sort=cost&qa=r11-performance-cache');
    await expect(page.getByText('5,000 ranked evidence rows', { exact: true })).toBeVisible();

    const startedAt = performance.now();
    await page.reload();
    await expect(page.getByText('5,000 ranked evidence rows', { exact: true })).toBeVisible();
    const elapsedMs = performance.now() - startedAt;

    expect(usageRequests, 'A complete loaded snapshot should be reused on reload instead of issuing /api/usage.').toBe(0);
    expect(
      elapsedMs,
      `Cached 5k reload took ${formatMs(elapsedMs)}, exceeding the ${formatMs(budgetsMs.cachedReload5k)} RC budget; inspect snapshot hydration and duplicate startup work.`,
    ).toBeLessThanOrEqual(budgetsMs.cachedReload5k);
    await attachEvidence(testInfo, 'cached-reload-5k', { elapsedMs, budgetMs: budgetsMs.cachedReload5k, rows: 5_000, usageRequests });
  });

  test('refreshes exactly one appended synthetic record inside the refresh budget', async ({ page }, testInfo) => {
    const refreshedRows = syntheticRows(5_001);
    refreshedRows.at(-1).thread_name = 'synthetic-appended-thread';
    refreshedRows.at(-1).thread_key = 'synthetic-appended-thread';
    await installSyntheticBoot(page, { rowCount: 5_000, limit: 5_000, totalRows: 5_000, apiToken: 'performance-token' });
    let usageRequests = 0;
    await page.route('**/api/usage?**', async route => {
      usageRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(syntheticPayload(refreshedRows, { limit: 5_000, totalRows: 5_001, apiToken: 'performance-token' })),
      });
    });
    await page.goto('/?view=calls&sort=cost&qa=r11-performance-append');
    await expect(page.getByText('5,000 ranked evidence rows', { exact: true })).toBeVisible();

    const startedAt = performance.now();
    await page.getByRole('button', { name: 'Refresh all dashboard data' }).click();
    await expect(page.getByText('5,001 ranked evidence rows', { exact: true })).toBeVisible();
    await page.getByPlaceholder('Search calls, cwd, projects, models...').fill('synthetic-appended-thread');
    await expect(page.getByText('synthetic-appended-thread', { exact: true }).first()).toBeVisible();
    const elapsedMs = performance.now() - startedAt;

    expect(usageRequests, 'One appended-record refresh should issue exactly one bounded /api/usage request.').toBe(1);
    expect(
      elapsedMs,
      `One-record append refresh took ${formatMs(elapsedMs)}, exceeding the ${formatMs(budgetsMs.appendedRefresh5k)} RC budget; inspect query invalidation and model replacement.`,
    ).toBeLessThanOrEqual(budgetsMs.appendedRefresh5k);
    await attachEvidence(testInfo, 'appended-refresh-5k', {
      elapsedMs,
      budgetMs: budgetsMs.appendedRefresh5k,
      rowsBefore: 5_000,
      rowsAfter: 5_001,
      usageRequests,
    });
  });
});

async function installSyntheticBoot(page, { rowCount, limit, totalRows = rowCount, apiToken = '' }) {
  await page.addInitScript(
    ({ syntheticRowCount, syntheticLimit, syntheticTotalRows, syntheticApiToken }) => {
      const rows = Array.from({ length: syntheticRowCount }, (_, index) => ({
        record_id: `synthetic-call-${index}`,
        session_id: `synthetic-session-${index % 500}`,
        call_started_at: new Date(Date.UTC(2026, 6, 10, 12, 0, 0) - index * 1_000).toISOString(),
        thread_name: `synthetic-thread-${index % 500}`,
        thread_key: `synthetic-thread-${index % 500}`,
        model: index % 2 ? 'codex-1' : 'o4-mini',
        effort: index % 3 ? 'medium' : 'high',
        input_tokens: 1_000 + (index % 100),
        cached_input_tokens: 600 + (index % 50),
        output_tokens: 100 + (index % 20),
        reasoning_output_tokens: index % 10,
        total_tokens: 1_100 + (index % 120),
        estimated_cost_usd: (index % 25) / 1_000,
      }));
      window.__CODEX_USAGE_BOOT__ = {
        api_token: syntheticApiToken || undefined,
        context_api_enabled: false,
        refresh_jobs_available: false,
        history_scope: 'active',
        include_archived: false,
        limit: syntheticLimit,
        limit_label: syntheticLimit === 0 ? 'All' : String(syntheticLimit),
        has_more: syntheticRowCount < syntheticTotalRows,
        latest_refresh_at: 'synthetic-r11-initial',
        loaded_row_count: syntheticRowCount,
        total_available_rows: syntheticTotalRows,
        active_available_rows: syntheticTotalRows,
        rows,
      };
    },
    {
      syntheticRowCount: rowCount,
      syntheticLimit: limit,
      syntheticTotalRows: totalRows,
      syntheticApiToken: apiToken,
    },
  );
}

function syntheticRows(rowCount) {
  return Array.from({ length: rowCount }, (_, index) => ({
    record_id: `synthetic-call-${index}`,
    session_id: `synthetic-session-${index % 500}`,
    call_started_at: new Date(Date.UTC(2026, 6, 10, 12, 0, 0) - index * 1_000).toISOString(),
    thread_name: `synthetic-thread-${index % 500}`,
    thread_key: `synthetic-thread-${index % 500}`,
    model: index % 2 ? 'codex-1' : 'o4-mini',
    effort: index % 3 ? 'medium' : 'high',
    input_tokens: 1_000 + (index % 100),
    cached_input_tokens: 600 + (index % 50),
    output_tokens: 100 + (index % 20),
    reasoning_output_tokens: index % 10,
    total_tokens: 1_100 + (index % 120),
    estimated_cost_usd: (index % 25) / 1_000,
  }));
}

function syntheticPayload(rows, { limit, totalRows = rows.length, apiToken }) {
  return {
    api_token: apiToken,
    context_api_enabled: false,
    refresh_jobs_available: false,
    history_scope: 'active',
    include_archived: false,
    limit,
    limit_label: String(limit),
    has_more: rows.length < totalRows,
    latest_refresh_at: `synthetic-r11-${rows.length}`,
    loaded_row_count: rows.length,
    total_available_rows: totalRows,
    active_available_rows: totalRows,
    rows,
  };
}

async function openCallsAndMeasure(page) {
  const startedAt = performance.now();
  await page.goto('/?view=calls&sort=cost&qa=r11-performance');
  await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible({ timeout: budgetsMs.startup100k });
  await expect(page.getByRole('table', { name: 'Model calls' })).toBeVisible({ timeout: budgetsMs.startup100k });
  return performance.now() - startedAt;
}

async function expectVirtualizedRowWindow(page, totalRows) {
  const table = page.getByRole('table', { name: 'Model calls' });
  await expect(table).toHaveAttribute('aria-rowcount', String(totalRows + 1));
  const scroller = page.locator('[data-virtualized="true"]').filter({ has: table });
  await expect(scroller).toHaveAttribute('data-virtualized', 'true');
  const renderedRows = await table.locator('tbody tr').count();
  expect(
    renderedRows,
    `${totalRows.toLocaleString()} logical rows rendered ${renderedRows.toLocaleString()} DOM rows; EvidenceGrid should keep the browser window below 100 rows.`,
  ).toBeLessThan(100);
  return renderedRows;
}

async function attachEvidence(testInfo, name, evidence) {
  await testInfo.attach(`${name}.json`, {
    body: Buffer.from(`${JSON.stringify({ scenario: name, ...evidence }, null, 2)}\n`),
    contentType: 'application/json',
  });
}

function formatMs(value) {
  return `${Math.round(value).toLocaleString()}ms`;
}
