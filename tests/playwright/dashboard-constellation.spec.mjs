import { expect, test } from '@playwright/test';

test.describe('overview visualization contract', () => {
  test('renders nonblank overview visualizations without restoring the removed 3D section', async ({ page }) => {
    const browserIssues = collectBrowserIssues(page);

    await page.setViewportSize({ width: 1600, height: 900 });
    await page.goto('/?view=overview&qa=r11-overview-visualizations');
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();

    await expect(page.getByTestId('usage-constellation')).toHaveCount(0);

    const charts = page.getByTestId('visualization-chart');
    await expect(charts).toHaveCount(2);

    for (const chart of await charts.all()) {
      await chart.scrollIntoViewIfNeeded();
      await expect(chart.locator('svg')).toBeVisible();
      const contract = await chart.evaluate(element => {
        const rect = element.getBoundingClientRect();
        const svg = element.querySelector('svg');
        const svgRect = svg?.getBoundingClientRect();
        return {
          documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          height: rect.height,
          width: rect.width,
          svgHeight: svgRect?.height ?? 0,
          svgWidth: svgRect?.width ?? 0,
          textLength: element.textContent?.trim().length ?? 0,
        };
      });
      expect(contract.documentOverflow).toBeLessThanOrEqual(2);
      expect(contract.width).toBeGreaterThan(240);
      expect(contract.height).toBeGreaterThan(180);
      expect(contract.svgWidth).toBeGreaterThan(200);
      expect(contract.svgHeight).toBeGreaterThan(140);
      expect(contract.textLength).toBeGreaterThan(20);
    }

    expect(browserIssues).toEqual([]);
  });

  test('keeps overview visual evidence contained on narrow desktop-style panes', async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 450 });
    await page.goto('/?view=overview&qa=r11-overview-visualizations-narrow');
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();

    const contract = await page.evaluate(() => ({
      documentOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      charts: Array.from(document.querySelectorAll('[data-testid="visualization-chart"]')).map(element => {
        const rect = element.getBoundingClientRect();
        return { width: rect.width, height: rect.height };
      }),
    }));

    expect(contract.documentOverflow).toBeLessThanOrEqual(2);
    expect(contract.charts).toHaveLength(2);
    for (const chart of contract.charts) {
      expect(chart.width).toBeGreaterThan(200);
      expect(chart.height).toBeGreaterThan(160);
    }
  });
});

function collectBrowserIssues(page) {
  const issues = [];
  page.on('console', message => {
    if (message.type() === 'error' || message.type() === 'warning') {
      issues.push(`${message.type()}: ${message.text()}`);
    }
  });
  page.on('pageerror', error => issues.push(`pageerror: ${error.message}`));
  return issues;
}
