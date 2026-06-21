import { expect, test } from '@playwright/test';

test.describe('diagnostics dashboard smoke', () => {
  test('renders diagnostics panels with explicit refresh control', async ({ page }) => {
    await page.goto('/dashboard.html?view=diagnostics');

    await expect(page.getByRole('button', { name: 'Diagnostics', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.locator('#diagnosticsPanel')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Refresh diagnostics' })).toBeVisible();
    await expect(page.locator('#diagnosticsPanel')).not.toContainText(
      'Live API required for diagnostics refresh',
    );

    for (const heading of [
      'Overview',
      'Tool Output',
      'Commands',
      'Git Interactions',
      'File Reads',
      'Read Productivity',
      'Concentration',
    ]) {
      await expect(page.getByRole('heading', { name: heading })).toBeVisible();
    }
  });
});
