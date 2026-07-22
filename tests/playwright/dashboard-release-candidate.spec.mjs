import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

const workspaces = [
  ['Home', '/?view=home&qa=r11-accessibility'],
  ['Calls', '/?view=explore&mode=calls&qa=r11-accessibility'],
  ['Threads', '/?view=explore&mode=threads&thread=thread-9f3a1c&qa=r11-accessibility'],
  ['Call Investigator', '/?view=evidence&kind=call&record=fixture-call-2&qa=r11-accessibility'],
  ['Limits', '/?view=limits&qa=r11-accessibility'],
  ['Settings', '/?view=settings&qa=r11-accessibility'],
];

const viewports = [
  ['desktop', { width: 1600, height: 900 }],
  ['tablet', { width: 1024, height: 768 }],
  ['mobile', { width: 390, height: 844 }],
];

test.describe('R11 dashboard release candidate', () => {
  test('defines and gates the release-candidate command in one Chromium CI job', async () => {
    const packageJson = JSON.parse(await readFile(path.join(repoRoot, 'package.json'), 'utf8'));
    expect(packageJson.scripts['dashboard:release-candidate']).toBe(
      'REACT_DASHBOARD_WEB_SERVER=1 playwright test tests/playwright/dashboard-release-candidate.spec.mjs --project=chromium-desktop',
    );

    const workflow = await readFile(path.join(repoRoot, '.github/workflows/ci.yml'), 'utf8');
    const hardeningJob = workflow.split('\n  hardening_dashboard:\n')[1]?.split(/\n  [a-z][a-z0-9_-]*:\n/)[0] || '';
    const npmCi = hardeningJob.indexOf('run: npm ci');
    const installChromium = hardeningJob.indexOf('run: npx playwright install --with-deps chromium');
    const releaseCandidate = hardeningJob.indexOf('run: npm run dashboard:release-candidate');

    expect(npmCi, 'hardening_dashboard runs npm ci').toBeGreaterThanOrEqual(0);
    expect(installChromium, 'hardening_dashboard installs Chromium').toBeGreaterThan(npmCi);
    expect(releaseCandidate, 'hardening_dashboard runs the release-candidate gate').toBeGreaterThan(installChromium);
  });

  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'This spec owns its viewport and media matrix.');
    test.setTimeout(180_000);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
  });

  test('passes the workspace accessibility and viewport matrix', async ({ page }) => {
    const browserIssues = collectBrowserIssues(page);
    const axeIssues = [];

    for (const [viewportName, viewport] of viewports) {
      await page.setViewportSize(viewport);

      for (const [workspaceName, path] of workspaces) {
        browserIssues.length = 0;
        await openWorkspace(page, workspaceName, path);
        const audit = await accessibilityAudit(page);
        const axeViolations = await seriousAxeViolations(page);

        expect(audit, `${viewportName} ${workspaceName} accessibility audit`).toEqual({
          documentOverflow: expect.any(Number),
          duplicateIds: [],
          emptyHeadings: [],
          landmarkCount: 1,
          unnamedControls: [],
        });
        expect(audit.documentOverflow, `${viewportName} ${workspaceName} document overflow`).toBeLessThanOrEqual(2);
        if (axeViolations.length > 0) axeIssues.push({ viewportName, workspaceName, violations: axeViolations });
        expect(browserIssues, `${viewportName} ${workspaceName} console/page errors`).toEqual([]);
      }
    }

    expect(axeIssues, 'serious or critical Axe violations').toEqual([]);
  });

  test('keeps the dense toolbar and Threads controls compact without wrapping commands', async ({ page }) => {
    for (const viewport of [{ width: 2048, height: 900 }, { width: 1280, height: 720 }]) {
      await page.setViewportSize(viewport);
      await openWorkspace(page, 'Threads', '/?view=explore&mode=threads&thread=thread-9f3a1c&qa=r11-toolbar-density');

      const geometry = await page.evaluate(() => {
        const box = element => {
          const rect = element?.getBoundingClientRect();
          return rect
            ? { height: rect.height, width: rect.width, top: rect.top, bottom: rect.bottom }
            : null;
        };
        const heading = Array.from(globalThis.document.querySelectorAll('h1'))
          .find(element => element.textContent?.trim() === 'Threads');
        const buttons = Array.from(globalThis.document.querySelectorAll('button'))
          .filter(element => ['Export thread calls', 'Reset view'].includes(element.textContent?.trim() || ''));
        return {
          documentOverflow: globalThis.document.documentElement.scrollWidth
            - globalThis.document.documentElement.clientWidth,
          filters: box(globalThis.document.querySelector('[aria-label="Dashboard filters"]')),
          pageHeader: box(heading?.closest('header') || null),
          rowLimit: box(globalThis.document.querySelector('[aria-label="Analysis scope"]')),
          toolbar: box(globalThis.document.querySelector('[aria-label="Dashboard toolbar"]')),
          wrappedCommands: buttons
            .filter(element => element.getBoundingClientRect().height > 44)
            .map(element => element.textContent?.trim()),
          workspace: box(globalThis.document.querySelector('main')),
        };
      });

      expect(geometry.documentOverflow, `${viewport.width}px document overflow`).toBeLessThanOrEqual(2);
      expect(geometry.toolbar?.height, `${viewport.width}px toolbar height`)
        .toBeLessThanOrEqual(viewport.width >= 1720 ? 84 : 132);
      expect(geometry.rowLimit?.bottom, `${viewport.width}px row controls before page content`)
        .toBeLessThanOrEqual(geometry.pageHeader?.top ?? 0);
      expect(geometry.filters?.height, `${viewport.width}px filter strip height`).toBeLessThanOrEqual(72);
      expect(geometry.wrappedCommands, `${viewport.width}px wrapped page commands`).toEqual([]);
      if (viewport.width >= 1720) {
        expect(geometry.filters?.width, 'wide filter strip should fit its controls')
          .toBeLessThan((geometry.workspace?.width ?? 0) - 300);
      }
    }
  });

  test('reflows every workspace at a 200 percent desktop zoom equivalent', async ({ page }) => {
    const browserIssues = collectBrowserIssues(page);

    // A 1600 x 900 desktop viewport exposes 800 x 450 CSS pixels at 200% browser zoom.
    await page.setViewportSize({ width: 800, height: 450 });
    for (const [workspaceName, path] of workspaces) {
      browserIssues.length = 0;
      await openWorkspace(page, workspaceName, path);
      await expectDocumentContainment(page, `200% zoom ${workspaceName}`);
      expect(browserIssues, `200% zoom ${workspaceName} console/page errors`).toEqual([]);
    }
  });

  test('honors reduced motion and exposes visible keyboard focus in every workspace', async ({ page }) => {
    const browserIssues = collectBrowserIssues(page);
    await page.setViewportSize({ width: 1024, height: 768 });
    await page.emulateMedia({ reducedMotion: 'reduce' });

    for (const [workspaceName, path] of workspaces) {
      browserIssues.length = 0;
      await openWorkspace(page, workspaceName, path);
      await expect.poll(() => page.evaluate(() => globalThis.matchMedia('(prefers-reduced-motion: reduce)').matches)).toBe(true);

      const motion = await page.evaluate(() => Array.from(globalThis.document.querySelectorAll('*'))
        .filter(element => {
          const style = globalThis.getComputedStyle(element);
          const rect = element.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
        })
        .map(element => {
          const style = globalThis.getComputedStyle(element);
          return {
            animation: style.animationName,
            animationDuration: style.animationDuration,
            transitionDuration: style.transitionDuration,
          };
        })
        .filter(value => value.animation !== 'none' && durationMilliseconds(value.animationDuration) > 10));
      expect(motion, `${workspaceName} reduced-motion animations`).toEqual([]);

      await page.locator('body').press('Tab');
      const focus = await page.evaluate(() => {
        const element = globalThis.document.activeElement;
        if (!(element instanceof globalThis.HTMLElement) || element === globalThis.document.body) return null;
        const rect = element.getBoundingClientRect();
        const style = globalThis.getComputedStyle(element);
        return {
          label: element.getAttribute('aria-label') || element.textContent?.trim().slice(0, 80) || element.tagName,
          visible: rect.width > 0 && rect.height > 0 && rect.bottom > 0 && rect.top < globalThis.innerHeight,
          hasIndicator: style.outlineStyle !== 'none' || style.boxShadow !== 'none',
        };
      });
      expect(focus, `${workspaceName} first keyboard focus target`).not.toBeNull();
      expect(focus?.visible, `${workspaceName} focused control visibility`).toBe(true);
      expect(focus?.hasIndicator, `${workspaceName} focused control indicator`).toBe(true);
      expect(browserIssues, `${workspaceName} reduced-motion console/page errors`).toEqual([]);
    }
  });

  test('keeps chart and table evidence equivalent in every visualized workspace', async ({ page }) => {
    const browserIssues = collectBrowserIssues(page);
    await page.setViewportSize({ width: 1440, height: 900 });

    for (const [workspaceName, path] of workspaces) {
      browserIssues.length = 0;
      await openWorkspace(page, workspaceName, path);
      const visualizations = page.locator('[data-visualization-id]:visible');

      for (let index = 0; index < await visualizations.count(); index += 1) {
        const visualization = visualizations.nth(index);
        const id = await visualization.getAttribute('data-visualization-id');
        const title = (await visualization.getByRole('heading').first().textContent())?.trim();
        const summary = (await visualization.locator('footer').textContent())?.trim();
        const chartButton = visualization.getByRole('button', { name: 'Chart view' });
        const tableButton = visualization.getByRole('button', { name: 'Table view' });

        await expect(chartButton, `${workspaceName} ${id} chart control`).toHaveAttribute('aria-pressed', 'true');
        await expect(visualization.getByRole('region', { name: `${title} chart` })).toBeVisible();
        await tableButton.click();
        await expect(tableButton).toHaveAttribute('aria-pressed', 'true');

        const tableRegion = visualization.getByRole('region', { name: `${title} table` });
        await expect(tableRegion).toBeVisible();
        expect(await tableRegion.getByRole('row').count(), `${workspaceName} ${id} table evidence rows`).toBeGreaterThan(1);
        expect((await visualization.locator('footer').textContent())?.trim(), `${workspaceName} ${id} summary`).toBe(summary);

        await chartButton.click();
        await expect(chartButton).toHaveAttribute('aria-pressed', 'true');
      }

      expect(browserIssues, `${workspaceName} chart/table console/page errors`).toEqual([]);
    }
  });

  test('keeps simplified navigation stable while preserving the browser-local preference', async ({ page }) => {
    await openWorkspace(page, 'Home', '/?view=home&qa=release-n-preference');
    const primary = page.getByRole('navigation', { name: 'Primary' });
    for (const label of ['Home', 'Explore', 'Limits']) {
      await expect(primary.getByRole('button', { name: label, exact: true }), `${label} baseline navigation`).toBeVisible();
    }
    await expect(page.getByRole('group', { name: 'Utility' }).getByRole('button', { name: 'Settings' })).toBeVisible();

    await openWorkspace(page, 'Settings', '/?view=settings&settings=advanced&qa=release-n-preference');
    await page.getByRole('button', { name: 'Advanced', exact: true }).click();
    const toggle = page.getByRole('checkbox', { name: 'Show compatibility and Labs links' });
    await toggle.check();
    expect(await page.evaluate(() => localStorage.getItem('codex-usage-dashboard-show-compatibility-labs-v1'))).toBe('true');
    await expect(page.getByRole('heading', { name: 'Compatibility Labs' })).toBeVisible();
    await openWorkspace(page, 'Settings', '/?view=settings&settings=advanced&qa=release-n-preference-reload');
    await page.getByRole('button', { name: 'Advanced', exact: true }).click();
    await expect(page.getByRole('checkbox', { name: 'Show compatibility and Labs links' })).toBeChecked();
    await expect(page.getByRole('heading', { name: 'Compatibility Labs' })).toBeVisible();
    await expect(primary.getByRole('button', { name: 'Investigate', exact: true })).toHaveCount(0);
    await expect(primary.getByRole('button', { name: 'Compression Lab', exact: true })).toHaveCount(0);

    await page.getByRole('checkbox', { name: 'Show compatibility and Labs links' }).uncheck();
    await openWorkspace(page, 'Settings', '/?view=settings&settings=advanced&qa=release-n-preference-reset');
    await page.getByRole('button', { name: 'Advanced', exact: true }).click();
    await expect(page.getByRole('checkbox', { name: 'Show compatibility and Labs links' })).not.toBeChecked();
    await expect(page.getByRole('heading', { name: 'Compatibility Labs' })).toHaveCount(0);
    await expect(primary.getByRole('button', { name: 'Investigate', exact: true })).toHaveCount(0);
    await expect(primary.getByRole('button', { name: 'Compression Lab', exact: true })).toHaveCount(0);
  });

  test('keeps direct lifecycle routes reachable with their maturity banners', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('codex-usage-dashboard-show-compatibility-labs-v1', 'false'));
    const routes = [
      ['Investigate', '/?view=investigator&qa=release-n-direct', 'Feature maturity: Available during transition'],
      ['Compression Lab', '/?view=compression-lab&qa=release-n-direct', 'Feature maturity: Available during transition'],
      ['Cache And Context Lab', '/?view=cache-context&qa=release-n-direct', 'Feature maturity: Available during transition'],
      ['Reports', '/?view=reports&qa=release-n-direct', 'Feature maturity: Available during transition'],
      ['Diagnostics Notebook', '/?view=diagnostics&qa=release-n-direct', 'Feature maturity: Available during transition'],
    ];
    for (const [workspace, route, banner] of routes) {
      await openWorkspace(page, workspace, route);
      await expect(page.getByRole('note', { name: banner })).toBeVisible();
    }
    await expect(
      page.getByRole('navigation', { name: 'Primary' }).getByRole('button', { name: 'Diagnostics Notebook', exact: true }),
    ).toHaveCount(0);
  });

  test('preserves the Call Investigator return route and thread context', async ({ page }) => {
    await openWorkspace(
      page,
      'Call Investigator',
      '/?view=evidence&kind=call&record=fixture-call-2&return=explore&return_mode=threads&thread=thread-9f3a1c&qa=release-n-return',
    );
    await page.getByRole('button', { name: 'Back to Explore' }).click();
    await expect(page.getByRole('heading', { name: 'Threads', exact: true })).toBeVisible();
    await expect(page).toHaveURL(/view=explore/);
    await expect(page).toHaveURL(/mode=threads/);
    await expect(page).not.toHaveURL(/record=|return=|kind=call/);
  });

  test('renders every conversational readiness state on Home', async ({ browser }, testInfo) => {
    const states = [
      ['ready', 'Ready'],
      ['restart-required', 'Restart required'],
      ['unavailable', 'Unavailable'],
      ['unknown', 'Checking'],
    ];
    for (const [state, label] of states) {
      const context = await browser.newContext({ baseURL: testInfo.project.use.baseURL });
      const statePage = await context.newPage();
      const browserIssues = collectBrowserIssues(statePage);
      await statePage.addInitScript(readiness => {
        window.__CODEX_USAGE_BOOT__ = {
          rows: [],
          loaded_row_count: 0,
          total_available_rows: 0,
          limit: 500,
          history_scope: 'active',
          conversational_analysis: readiness,
        };
      }, {
        schema: 'codex-usage-tracker-conversational-readiness-v1',
        state,
        summary: state === 'ready' ? 'Local checks passed.' : `Readiness is ${state}.`,
        next_action: null,
        evidence: [],
      });
      await openWorkspace(statePage, 'Home', '/?view=home&qa=release-n-readiness');
      const readiness = statePage.getByRole('region', { name: 'Home status' })
        .getByRole('article')
        .filter({ hasText: 'Conversational analysis' });
      await expect(readiness.getByText(label, { exact: true }).first()).toBeVisible();
      await expect(readiness).toContainText('profile');
      expect(browserIssues, `${state} readiness console/page errors`).toEqual([]);
      await context.close();
    }
  });

  test('renders Release N shell copy in the selected locale without English fallback', async ({ page }) => {
    const englishCatalog = JSON.parse(await readFile(
      path.join(repoRoot, 'src/codex_usage_tracker/plugin_data/dashboard/locales/en.json'),
      'utf8',
    ));
    const spanishCatalog = JSON.parse(await readFile(
      path.join(repoRoot, 'src/codex_usage_tracker/plugin_data/dashboard/locales/es.json'),
      'utf8',
    ));
    await page.addInitScript(catalogs => {
      window.__CODEX_USAGE_BOOT__ = {
        rows: [],
        loaded_row_count: 0,
        total_available_rows: 0,
        limit: 500,
        history_scope: 'active',
        language: 'en',
        language_direction: 'ltr',
        available_languages: [
          { code: 'en', english_name: 'English', native_name: 'English', dir: 'ltr' },
          { code: 'es', english_name: 'Spanish', native_name: 'Español', dir: 'ltr' },
        ],
        translation_catalog: { en: catalogs.english, es: catalogs.spanish },
      };
    }, { english: englishCatalog, spanish: spanishCatalog });
    await openWorkspace(page, 'Settings', '/?view=settings&qa=release-n-locale');
    await page.getByRole('button', { name: 'Application', exact: true }).click();
    await page.getByLabel('Language').selectOption('es');
    await page.getByRole('button', { name: /Advanced|Avanzado/, exact: true }).click();
    await expect(page.getByRole('checkbox', { name: 'Mostrar enlaces de compatibilidad y laboratorios' })).toBeVisible();
    await expect(page.getByText(
      'Esta preferencia local del navegador muestra enlaces directos temporales. Los laboratorios nunca aparecen en la navegación principal.',
    )).toBeVisible();

    await page.goto('/?view=diagnostics&qa=release-n-locale');
    await expect(page.getByRole('note', { name: 'Madurez de la función: Disponible durante la transición' })).toBeVisible();
    await expect(page.getByText('Disponible durante la transición', { exact: true })).toBeVisible();
    await expect(page.getByText('Highly experimental', { exact: true })).toHaveCount(0);
  });
});

async function openWorkspace(page, workspaceName, path) {
  await page.goto(path);
  await page.waitForLoadState('networkidle');
  await expect(page.getByRole('heading', { name: workspaceName, exact: true }).first()).toBeVisible();
  await expect(page.locator('vite-error-overlay')).toHaveCount(0);
}

function collectBrowserIssues(page) {
  const issues = [];
  page.on('console', message => {
    if (message.type() === 'error') issues.push(`console: ${message.text()}`);
  });
  page.on('pageerror', error => issues.push(`pageerror: ${error.message}`));
  return issues;
}

async function expectDocumentContainment(page, label) {
  const overflow = await page.evaluate(() => (
    Math.max(globalThis.document.documentElement.scrollWidth, globalThis.document.body.scrollWidth)
      - globalThis.document.documentElement.clientWidth
  ));
  expect(overflow, label).toBeLessThanOrEqual(2);
}

async function accessibilityAudit(page) {
  return page.evaluate(() => {
    const visible = element => {
      const style = globalThis.getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
    };
    const label = element => {
      const labelledBy = element.getAttribute('aria-labelledby');
      const labelledText = labelledBy
        ? labelledBy.split(/\s+/).map(id => globalThis.document.getElementById(id)?.textContent || '').join(' ')
        : '';
      const nativeLabel = 'labels' in element
        ? Array.from(element.labels || []).map(item => item.textContent || '').join(' ')
        : '';
      return (
        element.getAttribute('aria-label')
        || labelledText
        || nativeLabel
        || element.getAttribute('alt')
        || element.getAttribute('title')
        || element.textContent
        || ''
      ).replace(/\s+/g, ' ').trim();
    };
    const ids = Array.from(globalThis.document.querySelectorAll('[id]')).map(element => element.id);
    const duplicateIds = [...new Set(ids.filter((id, index) => id && ids.indexOf(id) !== index))];
    const unnamedControls = Array.from(globalThis.document.querySelectorAll('button, a[href], input, select, textarea'))
      .filter(visible)
      .filter(element => !label(element))
      .map(element => element.outerHTML.slice(0, 120));
    const emptyHeadings = Array.from(globalThis.document.querySelectorAll('h1, h2, h3, h4, h5, h6'))
      .filter(visible)
      .filter(element => !label(element))
      .map(element => element.outerHTML.slice(0, 120));

    return {
      documentOverflow: Math.max(globalThis.document.documentElement.scrollWidth, globalThis.document.body.scrollWidth)
        - globalThis.document.documentElement.clientWidth,
      duplicateIds,
      emptyHeadings,
      landmarkCount: globalThis.document.querySelectorAll('main').length,
      unnamedControls,
    };
  });
}

async function seriousAxeViolations(page) {
  const results = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    .analyze();
  return results.violations
    .filter(violation => violation.impact === 'serious' || violation.impact === 'critical')
    .map(violation => ({
      help: violation.help,
      id: violation.id,
      impact: violation.impact,
      targets: violation.nodes.slice(0, 5).map(node => node.target),
    }));
}

function durationMilliseconds(value) {
  return value.split(',').reduce((maximum, item) => {
    const duration = Number.parseFloat(item);
    const milliseconds = item.trim().endsWith('ms') ? duration : duration * 1000;
    return Math.max(maximum, milliseconds);
  }, 0);
}
