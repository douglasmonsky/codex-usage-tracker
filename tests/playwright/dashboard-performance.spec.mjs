import { expect, test } from '@playwright/test';
import { performance } from 'node:perf_hooks';

const budgetsMs = {
  startup5k: 15_000,
  allTime5k: 15_000,
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

  test('loads All time totals with a bounded 500-row evidence window', async ({ page }, testInfo) => {
    const evidenceRows = syntheticRows(500);
    await installSyntheticBoot(page, { rowCount: 500, limit: 500, totalRows: 5_000, apiToken: 'performance-token' });
    let usageRequests = 0;
    await page.route('**/api/usage?**', async route => {
      usageRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(syntheticPayload(evidenceRows, {
          limit: 500,
          totalRows: 5_000,
          apiToken: 'performance-token',
          loadWindow: 'all',
          revision: 'synthetic-r11-initial',
        })),
      });
    });
    await page.goto('./?view=calls&sort=cost&qa=r11-performance-all-time');
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();

    const startedAt = performance.now();
    await page.getByRole('button', { name: 'All time', exact: true }).click();
    await expect.poll(() => usageRequests).toBe(1);
    await expect(page.getByRole('button', { name: 'All time', exact: true })).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('region', { name: 'Analysis scope' })).toContainText('5,000 calls analyzed');
    await expect(page.getByRole('region', { name: 'Analysis scope' })).toContainText('500 detail rows cached');
    await expect(page.getByText('500 ranked evidence rows', { exact: true })).toBeVisible();
    const elapsedMs = performance.now() - startedAt;

    expect(usageRequests, 'All time should issue one bounded aggregate request.').toBe(1);
    expect(
      elapsedMs,
      `All time loading took ${formatMs(elapsedMs)}, exceeding the ${formatMs(budgetsMs.allTime5k)} RC budget; inspect aggregate queries and bounded model replacement.`,
    ).toBeLessThanOrEqual(budgetsMs.allTime5k);
    await attachEvidence(testInfo, 'all-time-5k', {
      elapsedMs,
      budgetMs: budgetsMs.allTime5k,
      evidenceRows: 500,
      totalRows: 5_000,
      usageRequests,
    });
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
    await page.goto('./?view=calls&qa=r11-performance-virtualized');
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

  test('restores a revision-matched All time snapshot across reload', async ({ page }, testInfo) => {
    await installSyntheticBoot(page, {
      rowCount: 0,
      limit: 500,
      totalRows: 5_000,
      apiToken: 'performance-token',
      defaultLoadWindow: 'all',
      shellBoot: true,
    });
    let usageRequests = 0;
    await page.route('**/api/usage?**', async route => {
      usageRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(syntheticPayload(syntheticRows(500), {
          limit: 500,
          totalRows: 5_000,
          apiToken: 'performance-token',
          loadWindow: 'all',
          revision: 'synthetic-r11-initial',
        })),
      });
    });
    await page.goto('./?view=calls&sort=cost&qa=r11-performance-cache');
    await expect(page.getByText('500 ranked evidence rows', { exact: true })).toBeVisible();
    await expect.poll(() => usageRequests).toBe(1);

    const startedAt = performance.now();
    await page.goto('./?view=calls&sort=cost&qa=r11-performance-cache');
    await expect(page.getByText('500 ranked evidence rows', { exact: true })).toBeVisible();
    const elapsedMs = performance.now() - startedAt;

    expect(usageRequests, 'Reload should restore the revision-matched IndexedDB snapshot without another /api/usage request.').toBe(1);
    expect(
      elapsedMs,
      `Cached 5k reload took ${formatMs(elapsedMs)}, exceeding the ${formatMs(budgetsMs.cachedReload5k)} RC budget; inspect snapshot hydration and duplicate startup work.`,
    ).toBeLessThanOrEqual(budgetsMs.cachedReload5k);
    await attachEvidence(testInfo, 'cached-reload-5k', {
      elapsedMs,
      budgetMs: budgetsMs.cachedReload5k,
      evidenceRows: 500,
      totalRows: 5_000,
      usageRequestsBeforeReload: 1,
      usageRequestsAfterReload: usageRequests,
    });
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
    await page.goto('./?view=calls&sort=cost&qa=r11-performance-append');
    await expect(page.getByText('5,000 ranked evidence rows', { exact: true })).toBeVisible();

    const startedAt = performance.now();
    const refreshButton = page.locator('[aria-label="Dashboard toolbar"]').getByRole('button', { name: 'Refresh' });
    await expect(refreshButton).toBeEnabled({ timeout: 30_000 });
    await refreshButton.click();
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

async function installSyntheticBoot(page, {
  rowCount,
  limit,
  totalRows = rowCount,
  apiToken = '',
  defaultLoadWindow = 'rows',
  shellBoot = false,
}) {
  await page.addInitScript(
    ({ syntheticRowCount, syntheticLimit, syntheticTotalRows, syntheticApiToken, syntheticDefaultLoadWindow, syntheticShellBoot }) => {
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
        load_window: 'rows',
        default_load_window: syntheticDefaultLoadWindow,
        limit: syntheticLimit,
        limit_label: syntheticLimit === 0 ? 'All' : String(syntheticLimit),
        has_more: syntheticRowCount < syntheticTotalRows,
        latest_refresh_at: 'synthetic-r11-initial',
        payload_cache_key: 'synthetic-r11-source',
        payload_cache_version: 2,
        shell_boot: syntheticShellBoot,
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
      syntheticDefaultLoadWindow: defaultLoadWindow,
      syntheticShellBoot: shellBoot,
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

function syntheticPayload(rows, {
  limit,
  totalRows = rows.length,
  apiToken,
  loadWindow = 'rows',
  revision = `synthetic-r11-${rows.length}`,
}) {
  return {
    api_token: apiToken,
    context_api_enabled: false,
    refresh_jobs_available: false,
    history_scope: 'active',
    include_archived: false,
    load_window: loadWindow,
    default_load_window: loadWindow,
    limit,
    limit_label: String(limit),
    has_more: rows.length < totalRows,
    latest_refresh_at: revision,
    payload_cache_key: 'synthetic-r11-source',
    payload_cache_version: 2,
    loaded_row_count: rows.length,
    total_available_rows: totalRows,
    active_available_rows: totalRows,
    rows,
  };
}

async function openCallsAndMeasure(page) {
  const startedAt = performance.now();
  await page.goto('./?view=calls&sort=cost&qa=r11-performance');
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
