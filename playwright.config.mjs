import { defineConfig, devices } from '@playwright/test';

const kernelPython = process.env.KERNEL_PYTHON || 'python3';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  webServer: {
    command: `PYTHONPATH=src ${JSON.stringify(kernelPython)} -m tests.kernel.console.serve_fixture`,
    url: 'http://127.0.0.1:8898/live',
    reuseExistingServer: false,
  },
  expect: {
    timeout: 10_000,
  },
  use: {
    baseURL: 'http://127.0.0.1:8898',
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
