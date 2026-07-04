import { expect, test } from '@playwright/test';

test.describe('React dashboard rewrite smoke', () => {
  test('renders and navigates the experimental dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await expect(page.getByText('Local data only').first()).toBeVisible();

    await page.getByRole('button', { name: /^Calls$/i }).click();
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toBeVisible();
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
  });

  test('filters, sorts, drills into calls, and exports aggregate CSV', async ({ page }) => {
await page.goto('/?view=calls');
await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();
await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toBeVisible();
await page.getByRole('button', { name: /Hide details/i }).click();
await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toHaveCount(0);
await expect(page.getByRole('table', { name: 'Model calls' })).toBeVisible();
await page.getByRole('button', { name: /Call Details/i }).click();
await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toBeVisible();

await page.getByLabel('Start date').fill('2026-07-04');
await page.getByLabel('End date').fill('2026-07-03');
await expect(page.getByText('Invalid date range')).toBeVisible();
await page.getByRole('button', { name: /Clear filters/i }).click();
await expect(page.getByText('Invalid date range')).toHaveCount(0);

await page.getByRole('button', { name: /Columns/i }).click();
    await expect(page.getByRole('checkbox', { name: 'Thread' })).toBeDisabled();
    await page.getByRole('checkbox', { name: 'Signal' }).uncheck();
    await expect(page.getByRole('columnheader', { name: /Signal/i })).toHaveCount(0);
    await page.getByRole('button', { name: /Columns/i }).click();

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
});
