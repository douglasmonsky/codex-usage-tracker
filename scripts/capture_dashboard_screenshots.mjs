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
  { name: 'dashboard-insights.png', query: '?view=overview&qa=docs-r11', heading: 'Overview', category: 'stable' },
  { name: 'dashboard-investigate.png', query: '?view=investigator&qa=docs-release-n', heading: 'Investigate', category: 'experimental' },
  { name: 'dashboard-compression-lab.png', query: '?view=compression-lab&qa=docs-release-n', heading: 'Compression Lab', category: 'experimental' },
  { name: 'dashboard-cache-context.png', query: '?view=cache-context&qa=docs-release-n', heading: 'Cache And Context Lab', category: 'transitioning' },
  { name: 'dashboard-reports.png', query: '?view=reports&qa=docs-release-n', heading: 'Reports', category: 'transitioning' },
  { name: 'dashboard-calls.png', query: '?view=calls&qa=docs-r11', heading: 'Calls', category: 'stable' },
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
    category: 'experimental',
  },
  {
    name: 'dashboard-call-investigator.png',
    query: '?view=call&record=fixture-call-2&return=calls&qa=docs-r11',
    heading: 'Call Investigator',
    category: 'contextual',
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
  ...['ready', 'restart-required', 'unavailable', 'unknown'].map(readiness => ({
    name: `dashboard-readiness-${readiness}.png`,
    query: `?view=overview&qa=docs-release-n-readiness-${readiness}`,
    heading: 'Overview',
    category: 'readiness',
    readiness,
  })),
];

for (const category of ['stable', 'experimental', 'transitioning', 'contextual']) {
  if (!captures.some(capture => capture.category === category)) {
    throw new Error(`Missing documentation screenshot route category: ${category}`);
  }
}
for (const readiness of ['ready', 'restart-required', 'unavailable', 'unknown']) {
  if (!captures.some(capture => capture.readiness === readiness)) {
    throw new Error(`Missing documentation screenshot readiness state: ${readiness}`);
  }
}

await mkdir(docsAssets, { recursive: true });
await mkdir(packagedAssets, { recursive: true });
const browser = await chromium.launch({ headless: true });

try {
  for (const capture of captures) {
    const page = await browser.newPage({
      colorScheme: 'light',
      reducedMotion: 'reduce',
      viewport: { width: 1600, height: 900 },
    });
    try {
      if (capture.readiness) await page.addInitScript(readinessBoot, capture.readiness);
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
    } finally {
      await page.close();
    }
  }
} finally {
  await browser.close();
}

function readinessBoot(state) {
  const rows = Array.from({ length: 8 }, (_, index) => ({
    record_id: `docs-readiness-${index}`,
    thread_id: `docs-thread-${index}`,
    model: 'gpt-5',
    timestamp: `2026-01-0${index + 1}T12:00:00Z`,
    input_tokens: 1000 + index,
    cached_input_tokens: 500,
    output_tokens: 200,
    reasoning_output_tokens: 50,
    total_tokens: 1250 + index,
  }));
  window.__CODEX_USAGE_BOOT__ = {
    rows,
    loaded_row_count: rows.length,
    total_available_rows: rows.length,
    limit: 500,
    history_scope: 'active',
    conversational_analysis: {
      schema: 'codex-usage-tracker-conversational-readiness-v1',
      state,
      summary: state === 'ready' ? 'Local checks passed.' : `Readiness is ${state}.`,
      next_action: null,
      evidence: [],
    },
  };
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
