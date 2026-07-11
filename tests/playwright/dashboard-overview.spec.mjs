import { expect, test } from '@playwright/test';

test.describe('answer-first Overview', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'This spec owns its responsive viewport checks.');
    page.on('pageerror', error => { throw error; });
  });

  test('keeps loaded metrics and recent-call evidence directly actionable', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto('/?view=overview&qa=r5-overview');
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
    await expect(page.locator('[aria-labelledby="overview-answer-title"]')).toBeVisible();
    await expect(page.getByLabel('Loaded usage metrics')).toContainText('cached');
    await expect(page.getByLabel('Loaded usage metrics')).toContainText('reasoning');
    await expect(page.getByTestId('visualization-chart').first().locator('svg')).toBeVisible();

    const table = page.getByRole('table', { name: 'Recent calls' });
    await expect(table).toBeVisible();
    const stickyContract = await table.evaluate(element => ({
      documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      firstColumn: getComputedStyle(element.querySelector('[role="columnheader"]')).position,
      overflow: getComputedStyle(element).overflow,
    }));
    expect(stickyContract.documentOverflow).toBeLessThanOrEqual(2);
    expect(stickyContract.firstColumn).toBe('sticky');
    expect(stickyContract.overflow).toContain('auto');

    await page.getByRole('row', { name: 'Open Call Investigator for thread-9f3a1c', exact: true }).click();
    await expect(page).toHaveURL(/view=call/);
    await expect(page).toHaveURL(/record=fixture-call-0/);
    await expect(page.getByRole('heading', { name: 'Call Investigator' })).toBeVisible();
  });

  test('places the first answer in the initial mobile viewport without document overflow', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/?view=overview&qa=r5-mobile-answer');
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
    const answer = page.locator('[aria-labelledby="overview-answer-title"]');
    await expect(answer).toBeVisible();

    const placement = await answer.evaluate(element => {
      const rect = element.getBoundingClientRect();
      return {
        documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        top: rect.top,
        visiblePixels: Math.max(0, document.documentElement.clientHeight - rect.top),
      };
    });
    expect(placement.documentOverflow).toBeLessThanOrEqual(2);
    expect(placement.top).toBeGreaterThanOrEqual(0);
    expect(placement.visiblePixels).toBeGreaterThanOrEqual(80);

    const screenshot = await page.screenshot({ animations: 'disabled' });
    await testInfo.attach('overview-mobile-first-answer.png', { body: screenshot, contentType: 'image/png' });
  });

  test('keeps the fallback answer visible while focused endpoints load', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript(() => {
      window.__CODEX_USAGE_BOOT__ = {
        api_token: 'overview-playwright-token',
        context_api_enabled: false,
        loaded_row_count: 1,
        total_available_rows: 1,
        latest_refresh_at: 'revision-r5',
        history_scope: 'active',
        rows: [{
          record_id: 'loaded-r5-call',
          call_started_at: '2026-07-10T12:00:00Z',
          thread_name: 'loaded-r5-thread',
          model: 'codex-1',
          effort: 'high',
          input_tokens: 1200,
          cached_input_tokens: 500,
          output_tokens: 180,
          total_tokens: 1380,
        }],
      };
    });
    await page.route('**/api/summary?**', async route => {
      await new Promise(resolve => setTimeout(resolve, 1_500));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schema: 'codex-usage-tracker-summary-v1',
          group_by: 'date',
          include_archived: false,
          privacy_mode: 'normal',
          rows: [{ group_key: '2026-07-10', model_calls: 1, input_tokens: 1200, cached_input_tokens: 500, output_tokens: 180, total_tokens: 1380, latest_event: '2026-07-10T12:00:00Z' }],
        }),
      });
    });
    await page.route('**/api/recommendations?**', async route => {
      await new Promise(resolve => setTimeout(resolve, 1_500));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          schema: 'codex-usage-tracker-recommendations-v1',
          filters: { include_archived: false },
          row_count: 1,
          total_matched_rows: 1,
          truncated: false,
          rows: [{
            record_id: 'loaded-r5-call',
            event_timestamp: '2026-07-10T12:00:00Z',
            thread_name: 'loaded-r5-thread',
            recommendation_score: 96,
            primary_recommendation: {
              key: 'context-bloat',
              severity: 'high',
              title: 'High context pressure',
              why: 'This call used a large share of its context window.',
              action: 'Start a fresh thread for unrelated work.',
            },
          }],
        }),
      });
    });

    await page.goto('/?view=overview&qa=r5-loading');
    await expect(page.getByText('Loading evidence', { exact: true })).toBeVisible();
    await expect(page.locator('[aria-labelledby="overview-answer-title"]')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'High context pressure is the clearest current signal' })).toBeVisible();
    await expect(page.getByText('Focused endpoints', { exact: true })).toBeVisible();
  });
});
