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
  {
    name: 'evidence-console-home.png',
    query: '?view=home&qa=docs-023',
    heading: 'Home',
    evidence: 'desktop',
  },
  {
    name: 'evidence-console-explore-calls.png',
    query: '?view=explore&mode=calls&qa=docs-023',
    heading: 'Calls',
  },
  {
    name: 'evidence-console-explore-threads.png',
    query: '?view=explore&mode=threads&thread=thread-9f3a1c&qa=docs-023',
    heading: 'Threads',
  },
  {
    name: 'evidence-console-limits.png',
    query: '?view=limits&qa=docs-023',
    heading: 'Limits',
  },
  {
    name: 'evidence-console-evidence-call.png',
    query: '?view=evidence&kind=call&record=fixture-call-2&return=explore&qa=docs-023',
    heading: 'Call Investigator',
  },
  {
    name: 'evidence-console-settings.png',
    query: '?view=settings&qa=docs-023',
    heading: 'Settings',
  },
  {
    name: 'evidence-console-legacy-reports.png',
    query: '?view=reports&qa=docs-023',
    heading: 'Reports',
  },
  {
    name: 'evidence-console-home-tablet.png',
    query: '?view=home&qa=docs-023-tablet',
    heading: 'Home',
    viewport: { width: 1024, height: 768 },
    evidence: 'tablet',
  },
  {
    name: 'evidence-console-home-mobile.png',
    query: '?view=home&qa=docs-023-mobile',
    heading: 'Home',
    viewport: { width: 390, height: 844 },
    evidence: 'mobile',
  },
  {
    name: 'evidence-console-home-zoom-200.png',
    query: '?view=home&qa=docs-023-zoom',
    heading: 'Home',
    viewport: { width: 800, height: 450 },
    evidence: 'zoom-200',
  },
  {
    name: 'evidence-console-home-reduced-motion.png',
    query: '?view=home&qa=docs-023-motion',
    heading: 'Home',
    reducedMotion: 'reduce',
    evidence: 'reduced-motion',
  },
  {
    name: 'evidence-console-home-keyboard.png',
    query: '?view=home&qa=docs-023-keyboard',
    heading: 'Home',
    keyboard: true,
    evidence: 'keyboard',
  },
];

for (const evidence of ['desktop', 'tablet', 'mobile', 'zoom-200', 'reduced-motion', 'keyboard']) {
  if (!captures.some(capture => capture.evidence === evidence)) {
    throw new Error(`Missing 0.23 screenshot evidence: ${evidence}`);
  }
}

await mkdir(docsAssets, { recursive: true });
await mkdir(packagedAssets, { recursive: true });
const browser = await chromium.launch({ headless: true });

try {
  for (const capture of captures) {
    const page = await browser.newPage({
      colorScheme: 'light',
      reducedMotion: capture.reducedMotion ?? 'no-preference',
      viewport: capture.viewport ?? { width: 1600, height: 900 },
    });
    try {
      if (capture.heading === 'Home') await page.addInitScript(homeBoot);
      await page.goto(new URL(capture.query, dashboardBaseUrl).href, { waitUntil: 'networkidle' });
      await page.getByRole('heading', { name: capture.heading, exact: true }).first().waitFor();
      await assertSyntheticFixture(page);
      if (capture.keyboard) await page.locator('body').press('Tab');
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

function homeBoot() {
  const rows = Array.from({ length: 8 }, (_, index) => ({
    record_id: `record-${index}`,
    session_id: `session-${index % 3}`,
    thread_id: `thread-${index % 3}`,
    model: index % 2 ? 'gpt-5' : 'gpt-5-mini',
    event_timestamp: `2026-07-22T1${index}:00:00Z`,
    input_tokens: 4000 + index * 500,
    cached_input_tokens: 2400 + index * 250,
    output_tokens: 600 + index * 50,
    reasoning_output_tokens: 150 + index * 10,
    total_tokens: 4750 + index * 560,
  }));
  window.__CODEX_USAGE_BOOT__ = {
    rows,
    loaded_row_count: rows.length,
    total_available_rows: rows.length,
    limit: 500,
    history_scope: 'active',
    latest_refresh_at: '2026-07-22T18:30:00Z',
    conversational_analysis: {
      schema: 'codex-usage-tracker-conversational-readiness-v1',
      state: 'ready',
      summary: 'Core MCP profile and local evidence service are ready.',
      next_action: null,
      configured_profile: 'core',
      runtime_version_matches: true,
      evidence: [],
    },
    home_summary: {
      schema: 'codex-usage-tracker-home-summary-v1',
      source_revision: 'synthetic-release-023',
      latest_refresh_at: '2026-07-22T18:30:00Z',
      latest_event_at: '2026-07-22T17:00:00Z',
      accounting: { physical_rows: 8, canonical_rows: 8, excluded_copied_rows: 0 },
      pricing: { configured: true, model_count: 2, official_model_count: 2, estimated_model_count: 0 },
      allowance: {
        configured: true,
        observed_usage: { available: true, source: 'synthetic', windows: [] },
        windows: [{ key: 'weekly', label: 'Weekly', remaining_percent: 64 }],
      },
      findings: [
        {
          finding_id: 'finding-cache', confidence: 'high', title: 'Low cache reuse in one thread',
          summary: 'Three synthetic calls repeatedly loaded fresh context.',
          action: 'Start a focused task after the shared setup step.',
          follow_up_prompt: 'Verify the low-cache calls and compare their context.',
          evidence: { kind: 'call', record_id: 'record-2' },
        },
        {
          finding_id: 'finding-effort', confidence: 'high', title: 'High effort dominates output',
          summary: 'Two synthetic calls explain most reasoning output.',
          action: 'Use medium effort for routine follow-up work.',
          follow_up_prompt: 'Compare high and medium effort usage.',
          evidence: { kind: 'call', record_id: 'record-5' },
        },
        {
          finding_id: 'finding-thread', confidence: 'high', title: 'One thread drives recent usage',
          summary: 'The largest synthetic thread contains four calls.',
          action: 'Inspect the thread before changing defaults.',
          follow_up_prompt: 'Open the highest-usage thread evidence.',
          evidence: { kind: 'call', record_id: 'record-7' },
        },
      ],
      recent_evidence: rows.slice(0, 5).map((row, index) => ({
        kind: 'call', evidence_id: row.record_id, label: `Synthetic thread ${index + 1}`,
        detail: `${row.model} · ${row.total_tokens.toLocaleString()} tokens`,
        observed_at: row.event_timestamp, record_id: row.record_id,
      })),
    },
  };
}

async function assertSyntheticFixture(page) {
  const state = await page.evaluate(() => ({
    apiToken: globalThis.__CODEX_USAGE_BOOT__?.api_token ?? '',
    bootRowCount: globalThis.__CODEX_USAGE_BOOT__?.rows?.length ?? 0,
    homeSourceRevision: globalThis.__CODEX_USAGE_BOOT__?.home_summary?.source_revision ?? '',
    hasEmbeddedPayload: Boolean(globalThis.document.getElementById('usage-data')?.textContent),
    text: globalThis.document.body.textContent ?? '',
  }));
  const syntheticHome = state.homeSourceRevision === 'synthetic-release-023' && state.bootRowCount === 8;
  const syntheticFixture = state.text.includes('Stored snapshot') && state.text.includes('8 calls analyzed');
  if (
    state.apiToken
    || state.hasEmbeddedPayload
    || (!syntheticHome && !syntheticFixture)
    || !state.text.includes('Local data only')
  ) {
    throw new Error('Dashboard documentation screenshots require the synthetic fixture payload.');
  }
}
