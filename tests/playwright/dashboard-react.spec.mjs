import { expect, test } from '@playwright/test';

test.describe('React dashboard rewrite smoke', () => {
  test('renders and navigates the experimental dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await expect(page.getByText('Local data only').first()).toBeVisible();

    await page.getByRole('button', { name: /^Calls$/i }).click();
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();
 await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toHaveCount(0);
    await expect(page.getByRole('table', { name: 'Model calls' })).toBeVisible();

    await page.getByRole('button', { name: /Open investigator for thread-9f3a1c codex-1/i }).click();
    await expect(page.getByRole('heading', { name: 'Call Investigator' })).toBeVisible();
    await expect(page).toHaveURL(/view=call/);
    await expect(page).toHaveURL(/record=fixture-call-0/);
    await page.getByRole('button', { name: /Next/i }).click();
    await expect(page.getByText('thread-7b2e91 / o4-mini')).toBeVisible();
    await page.getByRole('button', { name: /Back to Calls/i }).click();
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();

    await page.getByRole('button', { name: /^Reports$/i }).click();
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
    await expect(page.getByText('Weekly Credits').first()).toBeVisible();

    await page.getByRole('button', { name: /Cache And Context/i }).click();
    await expect(page.getByRole('heading', { name: 'Cache And Context Lab' })).toBeVisible();
    await page.getByRole('button', { name: /^Reports$/i }).click();
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
    await expect(page.getByText('Weekly Credits').first()).toBeVisible();
  });

  test('filters, sorts, drills into calls, and exports aggregate CSV', async ({ page }) => {
 await page.goto('/?view=calls');
 await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();
 await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toHaveCount(0);
 await expect(page.getByRole('table', { name: 'Model calls' })).toBeVisible();
 await page.getByRole('button', { name: /Call Details/i }).click();
 await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toBeVisible();
 await page.getByRole('button', { name: /Hide details/i }).click();
 await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toHaveCount(0);
await page.getByRole('button', { name: /Call Details/i }).click();
await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toBeVisible();

await page.getByText('More filters', { exact: true }).click();
await page.getByLabel('Start date').fill('2026-07-04');
await page.getByLabel('End date').fill('2026-07-03');
await expect(page.getByText('Invalid date range')).toBeVisible();
await page.getByRole('button', { name: /Clear filters/i }).click();
await expect(page.getByText('Invalid date range')).toHaveCount(0);

await page.getByRole('button', { name: 'Columns', exact: true }).click();
    await expect(page.getByRole('checkbox', { name: 'Thread' })).toBeDisabled();
    await page.getByRole('checkbox', { name: 'Signal' }).uncheck();
    await expect(page.getByRole('columnheader', { name: /Signal/i })).toHaveCount(0);
    await page.getByRole('button', { name: 'Columns', exact: true }).click();

    await page.getByRole('button', { name: 'Sort by Est. Cost' }).click();
    await expect(page.getByRole('columnheader', { name: /Est. Cost/i })).toHaveAttribute('aria-sort', 'descending');

  await page.getByPlaceholder('Search calls, cwd, projects, models...').fill('thread-3c8d4e');
  await expect(page).toHaveURL(/call_q=thread-3c8d4e/);
  await expect(page.getByRole('cell', { name: 'thread-3c8d4e', exact: true })).toBeVisible();
  await page.getByRole('row', { name: /thread-3c8d4e/ }).focus();
  await page.keyboard.press('Space');
  await expect(page.getByText('thread-3c8d4e / o3')).toBeVisible();
    await page.getByRole('tab', { name: /Evidence/i }).click();
    await expect(page.getByText('Raw context is gated')).toBeVisible();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export CSV' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('codex-calls-');
  });

  test('reuses live report evidence after returning from Cache and Context', async ({ page }) => {
    let reportRequests = 0;
    await page.addInitScript(() => {
      window.__CODEX_USAGE_BOOT__ = {
        api_token: 'playwright-token',
        context_api_enabled: false,
        latest_refresh_at: '2026-07-14T05:00:00Z',
        loaded_row_count: 1,
        total_available_rows: 1,
        rows: [{
          record_id: 'return-call',
          call_started_at: '2026-07-14T04:00:00Z',
          thread_name: 'return-thread',
          model: 'o5',
          effort: 'high',
          input_tokens: 1000,
          cached_input_tokens: 800,
          output_tokens: 100,
          total_tokens: 1100,
        }],
      };
    });
    await page.route('**/api/reports/pack?**', async route => {
      reportRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schema: 'codex-usage-tracker-reports-pack-v1',
          generated_at: '2026-07-14T05:00:00Z',
          reports: [{
            key: 'return-report',
            title: 'Return Navigation Report',
            status: 'Ready',
            owner: 'Playwright',
            description: 'Synthetic report evidence.',
          }],
          evidence: { 'return-report': { rows: [] } },
          row_count: 0,
          total_matched_rows: 1,
          raw_context_included: false,
        }),
      });
    });
    await page.route('**/api/summary?**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema: 'codex-usage-tracker-summary-v1',
        group_by: 'date',
        include_archived: false,
        privacy_mode: 'normal',
        rows: [],
      }),
    }));
    await page.route('**/api/threads?**', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        schema: 'codex-usage-tracker-threads-v1',
        include_archived: false,
        row_count: 0,
        total_matched_rows: 0,
        limit: 250,
        offset: 0,
        has_more: false,
        rows: [],
      }),
    }));

    await page.goto('/?view=reports');
    await expect(page.getByRole('heading', { name: 'Return Navigation Report' })).toBeVisible();
    await expect.poll(() => reportRequests).toBeGreaterThan(0);
    const initialReportRequests = reportRequests;
    await page.getByRole('button', { name: /Cache And Context/i }).click();
    await expect(page.getByRole('heading', { name: 'Cache And Context Lab' })).toBeVisible();
    await page.getByRole('button', { name: /^Reports$/i }).click();
    await expect(page.getByRole('heading', { name: 'Return Navigation Report' })).toBeVisible();
    await page.waitForTimeout(250);
    expect(reportRequests).toBe(initialReportRequests);
  });

  test('reuses live Investigator modules after return navigation', async ({ page }) => {
    const requestCounts = new Map();
    await page.addInitScript(() => {
      window.__CODEX_USAGE_BOOT__ = {
        api_token: 'playwright-token',
        context_api_enabled: true,
        latest_refresh_at: '2026-07-14T06:00:00Z',
        loaded_row_count: 1,
        total_available_rows: 1,
        rows: [{
          record_id: 'investigator-return-call',
          call_started_at: '2026-07-14T05:00:00Z',
          thread_name: 'investigator-return-thread',
          model: 'o5',
          effort: 'high',
          input_tokens: 1000,
          cached_input_tokens: 800,
          output_tokens: 100,
          total_tokens: 1100,
        }],
      };
    });
    await page.route('**/api/investigations/agentic?**', route => {
      countRequest(requestCounts, 'agentic');
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schema: 'codex-usage-tracker-agentic-investigation-v1',
          content_mode: 'aggregate_investigation',
          includes_indexed_content: false,
          includes_raw_fragments: false,
          privacy_mode: 'normal',
          goal: 'token_waste',
          filters: {},
          summary: {
            finding_count: 0,
            top_finding: null,
            confidence: 'low',
            source_reports: [],
          },
          findings: [],
          recommended_next_tools: [],
          caveats: [],
        }),
      });
    });
    await page.route('**/api/diagnostics/**', route => {
      const path = new URL(route.request().url()).pathname;
      countRequest(requestCounts, path);
      return route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'ready', section: path.split('/').at(-1) }),
      });
    });

    await page.goto('/?view=investigator');
    await expect(page.getByRole('heading', { name: 'Investigate' })).toBeVisible();
    await expect(page.getByRole('progressbar', { name: 'Loading investigation evidence' }))
      .toHaveCount(0);
    await expect.poll(() => requestCounts.size).toBe(11);
    const initialCounts = Object.fromEntries(requestCounts);

    await page.getByRole('button', { name: /^Settings$/i }).click();
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await page.getByRole('button', { name: /^Investigate$/i }).click();
    await expect(page.getByRole('heading', { name: 'Investigate' })).toBeVisible();
    await page.waitForTimeout(250);
    expect(Object.fromEntries(requestCounts)).toEqual(initialCounts);
  });

  test('retains completed Diagnostics modules and retries interrupted work', async ({ page }) => {
    const requestCounts = new Map();
    const commandWaiters = [];
    let allowCommands = false;
    await page.addInitScript(() => {
      window.__CODEX_USAGE_BOOT__ = {
        api_token: 'playwright-token',
        context_api_enabled: true,
        latest_refresh_at: '2026-07-14T06:30:00Z',
        loaded_row_count: 1,
        total_available_rows: 1,
        rows: [{
          record_id: 'diagnostics-return-call',
          call_started_at: '2026-07-14T05:30:00Z',
          thread_name: 'diagnostics-return-thread',
          model: 'o5',
          effort: 'high',
          input_tokens: 1000,
          cached_input_tokens: 800,
          output_tokens: 100,
          total_tokens: 1100,
        }],
      };
    });
    await page.route('**/api/diagnostics/**', async route => {
      const path = new URL(route.request().url()).pathname;
      countRequest(requestCounts, path);
      if (['/api/diagnostics/facts', '/api/diagnostics/tools', '/api/diagnostics/compactions'].includes(path)) {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            rows: [{ fact_type: 'cache', fact_name: 'large_uncached_input', associated_calls: 1 }],
            total_matched_rows: 1,
          }),
        });
      }
      if (path === '/api/diagnostics/fact-calls') {
        return route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ rows: [], total_matched_rows: 0 }),
        });
      }
      if (path === '/api/diagnostics/commands' && !allowCommands) {
        await new Promise(resolve => {
          commandWaiters.push(resolve);
        });
      }
      try {
        return await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({ status: 'ready', section: path.split('/').at(-1) }),
        });
      } catch {
        return undefined;
      }
    });

    await page.goto('/?view=diagnostics');
    const modules = page.getByLabel('Loading diagnostic snapshots modules');
    await expect(modules.getByText('Overview ready')).toBeVisible();
    await expect(modules.getByText('Commands loading')).toBeVisible();
    await expect(page.getByRole('progressbar', { name: 'Loading diagnostic snapshots' }))
      .toHaveAttribute('aria-valuenow', '9');
    const completedOverviewRequests = requestCounts.get('/api/diagnostics/overview');
    const pendingCommandRequests = requestCounts.get('/api/diagnostics/commands');

    await page.getByRole('button', { name: /^Settings$/i }).click();
    await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible();
    await page.getByRole('button', { name: /Diagnostics Notebook/i }).click();
    await expect.poll(() => requestCounts.get('/api/diagnostics/commands')).toBeGreaterThan(pendingCommandRequests);

    expect(requestCounts.get('/api/diagnostics/overview')).toBe(completedOverviewRequests);
    allowCommands = true;
    commandWaiters.splice(0).forEach(release => release());
    await expect(page.getByText('Live snapshots: 10')).toBeVisible();
  });

  test('opens direct call investigator URLs', async ({ page }) => {
    await page.goto('/?view=call&record=fixture-call-2');
    await expect(page.getByRole('heading', { name: 'Call Investigator' })).toBeVisible();
    await expect(page.getByText('thread-3c8d4e / o3')).toBeVisible();
    await expect(page.getByRole('button', { name: /^Calls$/i })).toHaveAttribute('aria-pressed', 'true');
  });

  test('hydrates direct call investigator URLs through the live call API', async ({ page }) => {
    const callRequests = [];
    await page.addInitScript(() => {
      window.__CODEX_USAGE_BOOT__ = {
        api_token: 'playwright-token',
        context_api_enabled: false,
        loaded_row_count: 1,
        rows: [
          {
            record_id: 'record-loaded',
            call_started_at: '2026-07-01T11:00:00Z',
            thread_name: 'loaded-thread',
            model: 'o4-mini',
            effort: 'medium',
            input_tokens: 900,
            cached_input_tokens: 300,
            output_tokens: 90,
            total_tokens: 990,
            estimated_cost_usd: 0.02,
          },
        ],
      };
    });
    await page.route('**/api/call?**', async route => {
      const request = route.request();
      callRequests.push({
        url: request.url(),
        token: request.headers()['x-codex-usage-token'],
      });
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schema: 'codex-usage-tracker-call-v1',
          record: {
            record_id: 'record-hydrated',
            call_started_at: '2026-07-01T12:00:00Z',
            thread_name: 'hydrated-thread',
            model: 'o5',
            effort: 'high',
            input_tokens: 2000,
            cached_input_tokens: 400,
            output_tokens: 250,
            total_tokens: 2250,
            estimated_cost_usd: 0.2,
            recommended_action: 'Review hydrated aggregate call.',
          },
          previous_record: {
            record_id: 'record-prev',
            call_started_at: '2026-07-01T11:55:00Z',
            thread_name: 'hydrated-thread',
            model: 'o5',
            effort: 'high',
            input_tokens: 1000,
            cached_input_tokens: 500,
            output_tokens: 100,
            total_tokens: 1100,
            estimated_cost_usd: 0.1,
          },
          next_record: {
            record_id: 'record-next',
            call_started_at: '2026-07-01T12:05:00Z',
            thread_name: 'hydrated-thread',
            model: 'o5',
            effort: 'high',
            input_tokens: 1100,
            cached_input_tokens: 550,
            output_tokens: 120,
            total_tokens: 1220,
            estimated_cost_usd: 0.12,
          },
        }),
      });
    });

    await page.goto('/?view=call&record=record-hydrated');
    await expect(page.getByRole('heading', { name: 'Call Investigator' })).toBeVisible();
    await expect(page.getByText('hydrated-thread / o5')).toBeVisible();
    await expect(page.getByText('Hydrated from /api/call')).toBeVisible();
    expect(callRequests).toHaveLength(1);
    expect(callRequests[0].token).toBe('playwright-token');
    expect(callRequests[0].url).toContain('record_id=record-hydrated');
  });

  test('runs Compression Lab analysis without leaking or overflowing aggregate evidence', async ({ page }) => {
    const requestTokens = [];
    const consoleErrors = [];
    const pageErrors = [];
    page.on('console', message => {
      if (message.type() === 'error') consoleErrors.push(message.text());
    });
    page.on('pageerror', error => pageErrors.push(error.message));
    await page.addInitScript(() => {
      window.__CODEX_USAGE_BOOT__ = {
        api_token: 'playwright-token',
        context_api_enabled: false,
        latest_refresh_at: '2026-07-14T08:00:00Z',
        loaded_row_count: 500,
        total_available_rows: 500,
        rows: [],
      };
    });
    let analysisStarted = false;
    await page.route('**/api/compression/profile?**', async route => {
      requestTokens.push(route.request().headers()['x-codex-usage-token']);
      const payload = analysisStarted ? compressionProfilePayload() : compressionMissingPayload();
      await route.fulfill({
        status: analysisStarted ? 200 : 404,
        contentType: 'application/json',
        body: JSON.stringify(payload),
      });
    });
    await page.route('**/api/compression/start?**', async route => {
      requestTokens.push(route.request().headers()['x-codex-usage-token']);
      analysisStarted = true;
      await route.fulfill({
        status: 202,
        contentType: 'application/json',
        body: JSON.stringify(compressionStatusPayload('running', 25)),
      });
    });
    await page.route('**/api/compression/status?**', async route => {
      requestTokens.push(route.request().headers()['x-codex-usage-token']);
      await new Promise(resolve => setTimeout(resolve, 100));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(compressionStatusPayload('completed', 100)),
      });
    });

    await page.goto('/?view=compression-lab');
    await expect(page.getByRole('heading', { name: 'Compression Lab' })).toBeVisible();
    await expect(page.getByText('No analysis for this scope yet')).toBeVisible();
    await page.getByRole('button', { name: 'Analyze usage' }).click();
    await expect(page.getByRole('progressbar', { name: 'Compression analysis progress' })).toBeVisible();
    await expect(page.getByText('240K', { exact: true })).toBeVisible();
    await expect(page.getByRole('table', { name: 'Compression opportunity families' })).toBeVisible();
    await expect(page.getByText('Not included')).toBeVisible();
    await expect(page.getByRole('progressbar', { name: 'Compression analysis progress' })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    expect(requestTokens).not.toContain(undefined);
    expect(new Set(requestTokens)).toEqual(new Set(['playwright-token']));
    expect(consoleErrors.filter(message => !message.includes('404 (Not Found)'))).toEqual([]);
    expect(pageErrors).toEqual([]);
  });
});

function countRequest(counts, key) {
  counts.set(key, (counts.get(key) ?? 0) + 1);
}

function compressionStatusPayload(status, percent) {
  return {
    schema: 'codex-usage-tracker-compression-api-v1',
    kind: 'status',
    run_id: 'compression-playwright',
    status,
    source_revision: 'generation:9',
    scope: { include_archived: false },
    coverage: {},
    cache: { reused: false, mode: null, request_reused: 'none' },
    progress: {
      percent,
      stage: status === 'completed' ? 'completed' : 'detectors',
      current_detector: status === 'completed' ? null : 'stale_context',
      completed_detectors: status === 'completed' ? 6 : 1,
      total_detectors: 6,
      records_examined: 500,
    },
    error: null,
    caveats: [],
    next: { poll_after_ms: 50 },
    profile: null,
  };
}

function compressionMissingPayload() {
  return {
    ...compressionStatusPayload('error', 0),
    kind: 'profile',
    run_id: null,
    error: { code: 'compression_run_not_found', message: 'No profile.' },
  };
}

function compressionProfilePayload() {
  return {
    ...compressionStatusPayload('completed', 100),
    kind: 'profile',
    cache: { reused: true, mode: 'exact', request_reused: 'completed' },
    profile: {
      candidate_count: 7,
      observed_exposure: { total: 1_200_000 },
      portfolio_estimate: { low: 120_000, likely: 240_000, high: 360_000 },
      families: [{
        family: 'stale_context',
        candidate_count: 4,
        adjusted_estimate: { low: 80_000, likely: 160_000, high: 240_000 },
      }],
      coverage: { call_count: 500, content_index_enabled: false },
      cache: { mode: 'exact', reused: true },
      duration_ms: 3,
      content_mode: 'aggregate',
      includes_indexed_content: false,
      includes_raw_fragments: false,
      warnings: [],
      caveats: ['Savings are heuristic ranges, not an OpenAI usage ledger.'],
    },
  };
}
