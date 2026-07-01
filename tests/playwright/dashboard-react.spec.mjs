import { expect, test } from '@playwright/test';

test.describe('React dashboard rewrite smoke', () => {
  test('renders and navigates the experimental dashboard', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
    await expect(page.getByText('Local data only').first()).toBeVisible();

    await page.getByRole('button', { name: /Calls/i }).click();
    await expect(page.getByRole('heading', { name: 'Calls', exact: true })).toBeVisible();
    await expect(page.getByRole('table')).toBeVisible();

    await page.getByRole('button', { name: /Reports/i }).click();
    await expect(page.getByRole('heading', { name: 'Reports' })).toBeVisible();
    await expect(page.getByText('Weekly Credits').first()).toBeVisible();
  });
});
