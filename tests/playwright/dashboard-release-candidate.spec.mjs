import { expect, test } from '@playwright/test';

const workspaces = [
  ['Overview', '/?view=overview&qa=r11-accessibility'],
  ['Investigate', '/?view=investigator&qa=r11-accessibility'],
  ['Calls', '/?view=calls&qa=r11-accessibility'],
  ['Call Investigator', '/?view=call&record=fixture-call-2&qa=r11-accessibility'],
  ['Threads', '/?view=threads&thread=thread-9f3a1c&qa=r11-accessibility'],
  ['Limits', '/?view=usage-drain&qa=r11-accessibility'],
  ['Cache And Context Lab', '/?view=cache-context&qa=r11-accessibility'],
  ['Diagnostics Notebook', '/?view=diagnostics&qa=r11-accessibility'],
  ['Reports', '/?view=reports&qa=r11-accessibility'],
  ['Settings', '/?view=settings&qa=r11-accessibility'],
];

const viewports = [
  ['desktop', { width: 1600, height: 900 }],
  ['tablet', { width: 1024, height: 768 }],
  ['mobile', { width: 390, height: 844 }],
];

test.describe('R11 dashboard release candidate', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'This spec owns its viewport and media matrix.');
    test.setTimeout(180_000);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
  });

  test('passes the workspace accessibility and viewport matrix', async ({ page }) => {
    const browserIssues = collectBrowserIssues(page);

    for (const [viewportName, viewport] of viewports) {
      await page.setViewportSize(viewport);

      for (const [workspaceName, path] of workspaces) {
        browserIssues.length = 0;
        await openWorkspace(page, workspaceName, path);
        const audit = await accessibilityAudit(page);

        expect(audit, `${viewportName} ${workspaceName} accessibility audit`).toEqual({
          documentOverflow: expect.any(Number),
          duplicateIds: [],
          emptyHeadings: [],
          landmarkCount: 1,
          unnamedControls: [],
        });
        expect(audit.documentOverflow, `${viewportName} ${workspaceName} document overflow`).toBeLessThanOrEqual(2);
        expect(browserIssues, `${viewportName} ${workspaceName} console/page errors`).toEqual([]);
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
      const visualizations = page.locator('[data-visualization-id]');

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

function durationMilliseconds(value) {
  return value.split(',').reduce((maximum, item) => {
    const duration = Number.parseFloat(item);
    const milliseconds = item.trim().endsWith('ms') ? duration : duration * 1000;
    return Math.max(maximum, milliseconds);
  }, 0);
}
