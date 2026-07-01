import { expect, test } from '@playwright/test';

test.describe('React dashboard rewrite smoke', () => {
  test('renders and navigates experimental dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await expect(page.getByText('Local data only').first()).toBeVisible();

    await page.getByRole('button', { name: /^Calls$/i }).click();
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Call Drill-Down' })).toBeVisible();
    await expect(page.getByRole('table', { name: 'Model calls' })).toBeVisible();

    await page.getByRole('button', { name: /^Reports$/i }).click();
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
    await expect(page.getByText('Weekly Credits').first()).toBeVisible();
  });

  test('filters, sorts, drills into calls, and exports aggregate CSV', async ({ page }) => {
    await page.goto('/?view=calls');
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();

    await page.getByRole('button', { name: /Columns/i }).click();
    await expect(page.getByRole('checkbox', { name: 'Thread' })).toBeDisabled();
    await page.getByRole('checkbox', { name: 'Signal' }).uncheck();
    await expect(page.getByRole('columnheader', { name: /Signal/i })).toHaveCount(0);
    await page.getByRole('button', { name: /Columns/i }).click();

    await page.getByRole('button', { name: 'Sort by Est. Cost' }).click();
    await expect(page.getByRole('columnheader', { name: /Est. Cost/i })).toHaveAttribute('aria-sort', 'descending');

    await page.getByPlaceholder('Search calls, threads, models...').fill('thread-3c8d4e');
    const callsTable = page.getByRole('table', { name: 'Model calls' });
    const matchingCall = callsTable.getByRole('cell', { name: 'thread-3c8d4e' });
    await expect(matchingCall).toBeVisible();
    await expect(callsTable.getByRole('cell', { name: 'thread-9f3a1c' })).toHaveCount(0);

    await matchingCall.click();
    await expect(page.getByText('thread-3c8d4e / o3')).toBeVisible();
    await expect(page.getByText('Uncached input').first()).toBeVisible();
    await expect(page.getByRole('tab', { name: /Summary/i })).toHaveAttribute('aria-selected', 'true');
    await page.getByRole('tab', { name: /Tokens/i }).click();
    await expect(page.getByText('Reasoning output')).toBeVisible();
  await page.getByRole('tab', { name: /Evidence/i }).click();
  await expect(page.getByText('Raw context is gated')).toBeVisible();
  await expect(page.getByText(/localhost dashboard server API token/i)).toBeVisible();

  const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /^Export$/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^codex-calls-\d{4}-\d{2}-\d{2}\.csv$/);
  });
});
