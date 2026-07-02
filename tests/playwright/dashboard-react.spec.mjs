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

    await page.getByRole('button', { name: /Open investigator/i }).click();
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

    await page.getByRole('button', { name: /Columns/i }).click();
    await expect(page.getByRole('checkbox', { name: 'Thread' })).toBeDisabled();
    await page.getByRole('checkbox', { name: 'Signal' }).uncheck();
    await expect(page.getByRole('columnheader', { name: /Signal/i })).toHaveCount(0);
    await page.getByRole('button', { name: /Columns/i }).click();

    await page.getByRole('button', { name: 'Sort by Est. Cost' }).click();
    await expect(page.getByRole('columnheader', { name: /Est. Cost/i })).toHaveAttribute('aria-sort', 'descending');

    await page.getByPlaceholder('Search calls, threads, models...').fill('thread-3c8d4e');
    await expect(page.getByRole('cell', { name: 'thread-3c8d4e' })).toBeVisible();
    await page.getByRole('row', { name: /thread-3c8d4e/ }).click();
    await expect(page.getByText('thread-3c8d4e / o3')).toBeVisible();
    await page.getByRole('tab', { name: /Evidence/i }).click();
    await expect(page.getByText('Raw context is gated')).toBeVisible();

    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /Export/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toContain('codex-calls-');
  });

  test('opens direct call investigator URLs', async ({ page }) => {
    await page.goto('/?view=call&record=fixture-call-2');
    await expect(page.getByRole('heading', { name: 'Call Investigator' })).toBeVisible();
    await expect(page.getByText('thread-3c8d4e / o3')).toBeVisible();
    await expect(page.getByRole('button', { name: /^Calls$/i })).toHaveAttribute('aria-pressed', 'true');
  });
});
