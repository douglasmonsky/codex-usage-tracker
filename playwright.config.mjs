import { defineConfig, devices } from '@playwright/test';

const baseURL = process.env.DASHBOARD_BASE_URL || 'http://127.0.0.1:8898';

export default defineConfig({
  testDir: './tests/playwright',
  timeout: 30_000,
  webServer: process.env.REACT_DASHBOARD_WEB_SERVER
    ? {
        command: 'npm --workspace frontend/dashboard run dev -- --port 5173',
        url: 'http://127.0.0.1:5173',
        reuseExistingServer: true,
      }
    : undefined,
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL,
    launchOptions: {
      args: ['--disable-gpu'],
    },
    trace: 'retain-on-failure',
  },
  reporter: [['list']],
  projects: [
    {
      name: 'chromium-desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      name: 'chromium-mobile',
      use: {
        ...devices['Pixel 5'],
        viewport: { width: 393, height: 851 },
      },
    },
  ],
});
