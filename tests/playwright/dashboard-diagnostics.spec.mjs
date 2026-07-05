import { expect, test } from '@playwright/test';

test.describe('diagnostics dashboard smoke', () => {
  test('renders diagnostics panels with explicit refresh control', async ({ page }) => {
    await page.goto('/?view=diagnostics');

    await expect(
      page.getByRole('button', { name: 'Diagnostics Notebook', exact: true }),
    ).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('heading', { name: 'Diagnostics Notebook' })).toBeVisible();
    await expect(page.getByText('Diagnostics Snapshot Matrix')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Refresh snapshots' })).toBeVisible();
    await expect(page.getByRole('main')).not.toContainText('Live diagnostic snapshots unavailable');

  for (const heading of [
    'Overview',
    'Tool Output',
    'Commands',
      'Git Interactions',
      'File Reads',
      'File Modifications',
      'Read Productivity',
      'Concentration',
    'What Is Driving Usage?',
    'Usage Drain',
  ]) {
    await expect(page.getByRole('heading', { name: heading, exact: true }).first()).toBeVisible();
  }
});
});
