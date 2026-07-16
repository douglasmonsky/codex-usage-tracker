import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const repositoryRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const docsAssets = path.join(repositoryRoot, 'docs', 'assets');
const packagedAssets = path.join(
  repositoryRoot,
  'src',
  'codex_usage_tracker',
  'plugin_data',
  'docs',
  'assets',
);
const dashboardBaseUrl = process.env.DASHBOARD_BASE_URL
  ?? 'http://127.0.0.1:4181/codex-usage-tracker-assets/react/';

const captures = [
  { name: 'dashboard-insights.png', query: '?view=overview&qa=docs-r11', heading: 'Overview' },
  { name: 'dashboard-calls.png', query: '?view=calls&qa=docs-r11', heading: 'Calls' },
  {
    name: 'dashboard-calls-preview.png',
    query: '?view=calls&record=fixture-call-2&qa=docs-r11',
    heading: 'Calls',
  },
  {
    name: 'dashboard-details.png',
    query: '?view=calls&record=fixture-call-2&qa=docs-r11',
    heading: 'Calls',
  },
  {
    name: 'dashboard-threads.png',
    query: '?view=threads&thread=thread-9f3a1c&qa=docs-r11',
    heading: 'Threads',
    expandThread: /^Expand calls for thread-9f3a$/i,
    region: /^Calls for thread-9f3a/i,
  },
  {
    name: 'dashboard-diagnostics.png',
    query: '?view=diagnostics&qa=docs-r11',
    heading: 'Diagnostics Notebook',
  },
  {
    name: 'dashboard-call-investigator.png',
    query: '?view=call&record=fixture-call-2&return=calls&qa=docs-r11',
    heading: 'Call Investigator',
  },
  {
    name: 'dashboard-call-investigator-preview.png',
    query: '?view=call&record=fixture-call-2&return=calls&qa=docs-r11',
    heading: 'Call Investigator',
  },
  {
    name: 'dashboard-call-investigator-evidence.png',
    query: '?view=call&record=fixture-call-2&return=calls&qa=docs-r11',
    heading: 'Call Investigator',
    scrollTo: 'Context Attribution',
  },
];

await mkdir(docsAssets, { recursive: true });
await mkdir(packagedAssets, { recursive: true });
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({
  colorScheme: 'light',
  reducedMotion: 'reduce',
  viewport: { width: 1600, height: 900 },
});

try {
  for (const capture of captures) {
    await page.goto(new URL(capture.query, dashboardBaseUrl).href, { waitUntil: 'networkidle' });
    await page.getByRole('heading', { name: capture.heading, exact: true }).first().waitFor();
    await assertSyntheticFixture(page);
    if (capture.expandThread) {
      await page.getByRole('row', { name: capture.expandThread }).click();
    }
    if (capture.region) {
      await page.getByRole('region', { name: capture.region }).waitFor();
    }
    if (capture.scrollTo) {
      await page.getByRole('heading', { name: capture.scrollTo, exact: true }).scrollIntoViewIfNeeded();
    }
    const bytes = await page.screenshot({ animations: 'disabled', type: 'png' });
    await Promise.all([
      writeFile(path.join(docsAssets, capture.name), bytes),
      writeFile(path.join(packagedAssets, capture.name), bytes),
    ]);
    console.log(`captured ${capture.name}`);
  }
} finally {
  await browser.close();
}

async function assertSyntheticFixture(page) {
  const state = await page.evaluate(() => ({
    apiToken: globalThis.__CODEX_USAGE_BOOT__?.api_token ?? '',
    hasEmbeddedPayload: Boolean(globalThis.document.getElementById('usage-data')?.textContent),
    text: globalThis.document.body.textContent ?? '',
  }));
  if (
    state.apiToken
    || state.hasEmbeddedPayload
    || !state.text.includes('Stored snapshot')
    || !state.text.includes('8 calls analyzed')
    || !state.text.includes('Local data only')
  ) {
    throw new Error('Dashboard documentation screenshots require the synthetic fixture payload.');
  }
}
