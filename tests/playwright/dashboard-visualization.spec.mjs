import { expect, test } from '@playwright/test';

const examples = [
  'allowance-change-point',
  'token-flow',
  'cache-frontier',
  'thread-lifecycle',
  'waste-matrix',
  'evidence-ledger',
];
const states = ['loading', 'empty', 'partial', 'insufficient-data', 'stale', 'error'];
const mobileExamples = examples;

test.describe('dashboard visualization contracts', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'This contract owns a fixed viewport.');
    await page.setViewportSize({ width: 1440, height: 900 });
  });

  test('renders six deterministic SVG examples without containment or browser errors', async ({ page }, testInfo) => {
    const browserIssues = collectBrowserIssues(page);

    for (const example of examples) {
      await page.goto(`./?lab=visualization-contract&example=${example}&state=ready&mode=chart`);
      const panel = page.locator('[data-visualization-id]').first();
      const chart = panel.getByTestId('visualization-chart');
      await expect(chart.locator('svg')).toBeVisible();
      expect(await chart.locator('path').count(), `${example} must render SVG paths`).toBeGreaterThan(2);
      await expectDocumentContainment(page);
      await captureStableScreenshot(panel, testInfo, `${example}.png`, 8_000);
    }

    expect(browserIssues).toEqual([]);
  });

  test('renders every non-ready state with deterministic evidence messaging', async ({ page }, testInfo) => {
    const browserIssues = collectBrowserIssues(page);

    for (const state of states) {
      await page.goto(`./?lab=visualization-contract&example=allowance-change-point&state=${state}&mode=chart`);
      const panel = page.locator('[data-visualization-id]').first();
      await expect(panel).toHaveAttribute('data-visualization-state', state);
      await expect(panel.locator('[role="status"], [role="alert"]').first()).toBeVisible();
      await expectDocumentContainment(page);
      await captureStableScreenshot(panel, testInfo, `state-${state}.png`, 3_000);
    }

    expect(browserIssues).toEqual([]);
  });

  test('keeps keyboard chart selection synchronized with the table and exports SVG', async ({ page }) => {
    const browserIssues = collectBrowserIssues(page);
    await page.goto('./?lab=visualization-contract&example=allowance-change-point&state=ready&mode=chart');

    const chartRegion = page.getByRole('region', { name: 'Weekly allowance regime evidence chart' });
    await chartRegion.focus();
    await chartRegion.press('ArrowRight');
    await expect(page.getByText('Selected Window: 2026-05-26')).toBeVisible();

    await page.getByRole('button', { name: 'Table view' }).click();
    const selectedRow = page.locator('tr[data-selection-key="week-05-26"]');
    await expect(selectedRow).toHaveAttribute('aria-selected', 'true');

    await page.getByRole('button', { name: 'Chart view' }).click();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: 'Export visualization as SVG' }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toBe('codex-allowance-change-point.svg');
    expect(browserIssues).toEqual([]);
  });

  test('contains all chart families and exposes wide-table scrolling on mobile', async ({ page }, testInfo) => {
    const browserIssues = collectBrowserIssues(page);
    await page.setViewportSize({ width: 390, height: 844 });

    for (const example of mobileExamples) {
      await page.goto(`./?lab=visualization-contract&example=${example}&state=ready&mode=chart`);
      const panel = page.locator('[data-visualization-id]').first();
      await expect(panel.getByTestId('visualization-chart').locator('svg')).toBeVisible();
      await expectDocumentContainment(page);
      await captureStableScreenshot(panel, testInfo, `mobile-${example}.png`, 8_000);
    }

    await page.goto('./?lab=visualization-contract&example=allowance-change-point&state=ready&mode=table');
    const tableRegion = page.getByRole('region', { name: 'Weekly allowance regime evidence table' });
    const tableFrame = tableRegion.locator('..');
    await expect(tableFrame).toHaveAttribute('data-overflow-right', 'true');
    const tableContract = await tableRegion.evaluate(element => ({
      canScroll: element.scrollWidth > element.clientWidth,
      firstColumnPosition: getComputedStyle(element.querySelector('th')).position,
      overflowX: getComputedStyle(element).overflowX,
    }));
    expect(tableContract).toMatchObject({ canScroll: true, firstColumnPosition: 'sticky', overflowX: 'auto' });
    await captureStableScreenshot(page.locator('[data-visualization-id]').first(), testInfo, 'mobile-table-overflow.png', 8_000);
    await tableRegion.evaluate(element => { element.scrollLeft = element.scrollWidth; });
    await expect(tableFrame).toHaveAttribute('data-overflow-right', 'false');
    await expectDocumentContainment(page);
    await captureStableScreenshot(page.locator('[data-visualization-id]').first(), testInfo, 'mobile-table-scrolled.png', 8_000);

    expect(browserIssues).toEqual([]);
  });
});

async function captureStableScreenshot(locator, testInfo, name, minimumBytes) {
  await locator.screenshot({ animations: 'disabled' });
  await locator.page().waitForTimeout(500);
  const path = testInfo.outputPath(name);
  const screenshot = await locator.screenshot({ animations: 'disabled', path });
  expect(screenshot.byteLength, `${name} must contain rendered pixels`).toBeGreaterThan(minimumBytes);
  await testInfo.attach(name, { path, contentType: 'image/png' });
}

function collectBrowserIssues(page) {
  const issues = [];
  page.on('console', message => {
    if (message.type() === 'error' || message.type() === 'warning') issues.push(`${message.type()}: ${message.text()}`);
  });
  page.on('pageerror', error => issues.push(`pageerror: ${error.message}`));
  return issues;
}

async function expectDocumentContainment(page) {
  const containment = await page.evaluate(() => ({
    documentWidth: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
    viewportWidth: document.documentElement.clientWidth,
    frameworkError: Boolean(document.querySelector('vite-error-overlay')),
  }));
  expect(containment.frameworkError).toBe(false);
  expect(containment.documentWidth - containment.viewportWidth).toBeLessThanOrEqual(2);
}
