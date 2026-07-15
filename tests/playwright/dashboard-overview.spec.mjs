import { expect, test } from '@playwright/test';

test.describe('overview evidence workspace', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'This spec owns its responsive viewport checks.');
    page.on('pageerror', error => { throw error; });
  });

  test('keeps loaded metrics, visualizations, and recent-call evidence directly actionable', async ({ page }) => {
    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto('/?view=overview&qa=r5-overview');
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
    await expect(page.getByLabel('Loaded usage metrics')).toContainText('cached');
    await expect(page.getByLabel('Loaded usage metrics')).toContainText('Reasoning');
    await expect(page.getByTestId('visualization-chart')).toHaveCount(2);
    await expect(page.getByTestId('visualization-chart').first().locator('svg')).toBeVisible();

    const table = page.getByRole('table', { name: 'Overview calls' });
    await expect(table).toBeVisible();
    const stickyContract = await table.evaluate(element => ({
      documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      firstColumn: getComputedStyle(element.querySelector('.sticky-column')).position,
      overflow: getComputedStyle(element.closest('section')?.querySelector('[data-layout-scroll="true"]')).overflow,
    }));
    expect(stickyContract.documentOverflow).toBeLessThanOrEqual(2);
    expect(stickyContract.firstColumn).toBe('sticky');
    expect(stickyContract.overflow).toContain('auto');

    await page.getByRole('button', { name: /Open investigator for thread-9f3a1c codex-1/i }).first().click();
    await expect(page).toHaveURL(/view=call/);
    await expect(page).toHaveURL(/record=fixture-call-0/);
    await expect(page.getByRole('heading', { name: 'Call Investigator' })).toBeVisible();
  });

  test('keeps token-flow labels and virtual-row actions inside constrained desktop layouts', async ({ page }) => {
    for (const viewport of [
      { width: 1280, stacked: true },
      { width: 1321, stacked: false },
    ]) {
      await page.setViewportSize({ width: viewport.width, height: 900 });
      await page.goto(`/?view=overview&qa=overview-layout-${viewport.width}`);
      await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();

      const charts = page.getByTestId('visualization-chart');
      await expect(charts).toHaveCount(2);
      const chartBounds = await charts.evaluateAll(elements => elements.map(element => {
        const rect = element.getBoundingClientRect();
        return { bottom: rect.bottom, height: rect.height, left: rect.left, right: rect.right, top: rect.top };
      }));
      if (viewport.stacked) {
        expect(chartBounds[1].top).toBeGreaterThanOrEqual(chartBounds[0].bottom - 2);
      } else {
        expect(chartBounds[1].top).toBeLessThan(chartBounds[0].bottom - 2);
        expect(chartBounds[1].left).toBeGreaterThanOrEqual(chartBounds[0].right - 2);
      }
    }

    await page.setViewportSize({ width: 1280, height: 900 });
    const flowChart = page.getByTestId('visualization-chart').nth(1);
    await expect(flowChart.locator('svg')).toBeVisible();
    const flowContract = await flowChart.evaluate(element => {
      const svg = element.querySelector('svg');
      if (!svg) throw new Error('Token-flow SVG was not rendered.');
      const svgBounds = svg.getBoundingClientRect();
      const labels = [...svg.querySelectorAll('text')]
        .map(label => {
          const rect = label.getBoundingClientRect();
          return { bottom: rect.bottom, left: rect.left, right: rect.right, text: label.textContent?.trim(), top: rect.top };
        })
        .filter(label => label.text);
      const collisions = labels.flatMap((label, index) => labels.slice(index + 1).filter(other => (
        Math.min(label.right, other.right) - Math.max(label.left, other.left) > 1
        && Math.min(label.bottom, other.bottom) - Math.max(label.top, other.top) > 1
      )).map(other => `${label.text}:${other.text}`));
      return {
        chartHeight: element.getBoundingClientRect().height,
        collisions,
        labelCount: labels.length,
        labelsInsideSvg: labels.every(label => (
          label.left >= svgBounds.left - 1
          && label.right <= svgBounds.right + 1
          && label.top >= svgBounds.top - 1
          && label.bottom <= svgBounds.bottom + 1
        )),
      };
    });
    expect(flowContract.chartHeight).toBeGreaterThanOrEqual(319);
    expect(flowContract.labelCount).toBeGreaterThan(1);
    expect(flowContract.labelsInsideSvg).toBe(true);
    expect(flowContract.collisions).toEqual([]);

    const actionGroup = page.getByRole('table', { name: 'Overview calls' }).locator('.table-action-group').first();
    await expect(actionGroup).toBeVisible();
    const actionContract = await actionGroup.evaluate(element => {
      const row = element.closest('tr');
      if (!row) throw new Error('Action group is not inside a table row.');
      const actions = element.getBoundingClientRect();
      const rowBounds = row.getBoundingClientRect();
      return {
        actionBounds: { bottom: actions.bottom, height: actions.height, left: actions.left, right: actions.right, top: actions.top },
        flexWrap: getComputedStyle(element).flexWrap,
        insideRow: actions.right <= rowBounds.right + 1 && actions.top >= rowBounds.top - 1 && actions.bottom <= rowBounds.bottom + 1,
        rowBounds: { bottom: rowBounds.bottom, height: rowBounds.height, left: rowBounds.left, right: rowBounds.right, top: rowBounds.top },
      };
    });
    expect(actionContract.flexWrap).toBe('nowrap');
    expect(actionContract.insideRow, JSON.stringify(actionContract)).toBe(true);
  });

  test('places overview summary in the initial mobile viewport without document overflow', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/?view=overview&qa=r5-mobile-answer');
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
    const metrics = page.getByLabel('Loaded usage metrics');
    await expect(metrics).toBeVisible();

    const placement = await metrics.evaluate(element => {
      const rect = element.getBoundingClientRect();
      return {
        documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        top: rect.top,
        visiblePixels: Math.max(0, document.documentElement.clientHeight - rect.top),
      };
    });
    expect(placement.documentOverflow).toBeLessThanOrEqual(2);
    expect(placement.top).toBeGreaterThanOrEqual(0);
    expect(placement.visiblePixels).toBeGreaterThanOrEqual(120);

    const screenshot = await page.screenshot({ animations: 'disabled' });
    await testInfo.attach('overview-mobile-summary.png', { body: screenshot, contentType: 'image/png' });
  });

  test('keeps fallback overview evidence visible while focused endpoints load', async ({ page }) => {
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
    await expect(page.getByRole('progressbar', { name: 'Loading overview evidence' })).toBeVisible();
    await expect(page.getByLabel('Loaded usage metrics')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();
    await expect(page.getByText('1 matching calls')).toBeVisible();
    await expect(page.getByText('Focused endpoints', { exact: true })).toBeVisible();
  });
});
