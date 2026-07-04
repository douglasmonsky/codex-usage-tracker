import { expect, test } from '@playwright/test';

const routes = [
  ['Overview', 'Overview', '/?view=overview&qa=visual-hardening'],
  ['Investigator', 'Investigator Workbench', '/?view=investigator&qa=visual-hardening'],
  ['Calls', 'Calls', '/?view=calls&qa=visual-hardening'],
  ['Call Investigator', 'Call Investigator', '/?view=call&record=fixture-call-2&qa=visual-hardening'],
  ['Threads', 'Thread Efficiency', '/?view=threads&thread=thread-9f3a1c&qa=visual-hardening'],
  ['Usage Drain Lab', 'Usage Drain Lab', '/?view=usage-drain&qa=visual-hardening'],
  ['Cache And Context Lab', 'Cache And Context Lab', '/?view=cache-context&qa=visual-hardening'],
  ['Diagnostics Notebook', 'Diagnostics Notebook', '/?view=diagnostics&qa=visual-hardening'],
  ['Reports', 'Reports', '/?view=reports&qa=visual-hardening'],
  ['Settings', 'Settings', '/?view=settings&qa=visual-hardening'],
];

const viewports = [
  ['desktop', { width: 1600, height: 900 }],
  ['tablet', { width: 1024, height: 768 }],
  ['mobile', { width: 390, height: 844 }],
];

test.describe('React dashboard visual hardening', () => {
  test('keeps dashboard routes contained and controls non-overlapping', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'This spec defines its own viewport matrix.');

    const browserIssues = [];
    page.on('console', message => {
      if (message.type() === 'error' || message.type() === 'warning') {
        browserIssues.push(`${message.type()}: ${message.text()}`);
      }
    });
    page.on('pageerror', error => browserIssues.push(`pageerror: ${error.message}`));

    for (const [viewportName, viewport] of viewports) {
      await page.setViewportSize(viewport);

      for (const [routeName, headingName, path] of routes) {
        browserIssues.length = 0;
        await page.goto(path);
        await page.waitForLoadState('networkidle');
        await expect(page.getByRole('heading', { name: headingName, exact: true })).toBeVisible();

        const audit = await page.evaluate(() => {
          const viewportWidth = document.documentElement.clientWidth;
          const allowedOverflowSelector = [
            '.primary-nav',
            '.table-scroll',
            '.chart-scroll',
            '.chart-scroll-shell',
            '.column-menu',
          ].join(',');
          const hiddenSelector = [
            '.sr-only',
            '[aria-hidden="true"]',
            '[hidden]',
            'input[type="hidden"]',
          ].join(',');

          function isVisible(element) {
            const style = getComputedStyle(element);
            const rect = element.getBoundingClientRect();
            return (
              rect.width > 0 &&
              rect.height > 0 &&
              rect.bottom > 0 &&
              rect.top < window.innerHeight &&
              style.visibility !== 'hidden' &&
              style.display !== 'none'
            );
          }

          function labelFor(element) {
            return (
              element.getAttribute('aria-label') ||
              element.getAttribute('title') ||
              element.textContent ||
              element.tagName
            )
              .replace(/\s+/g, ' ')
              .trim()
              .slice(0, 80);
          }

          const documentOverflow = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - viewportWidth;
          const offscreenControls = Array.from(document.querySelectorAll('button, a, input, select, textarea'))
            .filter(element => !element.closest(hiddenSelector))
            .filter(element => !element.closest(allowedOverflowSelector))
            .filter(isVisible)
            .map(element => {
              const rect = element.getBoundingClientRect();
              return {
                label: labelFor(element),
                left: Math.round(rect.left),
                right: Math.round(rect.right),
                width: Math.round(rect.width),
              };
            })
            .filter(rect => rect.left < -2 || rect.right > viewportWidth + 2);

          const controls = Array.from(document.querySelectorAll('button, a, input, select, textarea'))
            .filter(element => !element.closest(hiddenSelector))
            .filter(element => !element.closest(allowedOverflowSelector))
            .filter(isVisible)
            .map(element => ({ element, rect: element.getBoundingClientRect(), label: labelFor(element) }));

          const overlaps = [];
          for (let i = 0; i < controls.length; i += 1) {
            const first = controls[i];
            for (let j = i + 1; j < controls.length; j += 1) {
              const second = controls[j];
              if (first.element.contains(second.element) || second.element.contains(first.element)) continue;
              const xOverlap = Math.max(
                0,
                Math.min(first.rect.right, second.rect.right) - Math.max(first.rect.left, second.rect.left),
              );
              const yOverlap = Math.max(
                0,
                Math.min(first.rect.bottom, second.rect.bottom) - Math.max(first.rect.top, second.rect.top),
              );
              const area = xOverlap * yOverlap;
              if (area > 40) {
                overlaps.push({
                  first: first.label,
                  second: second.label,
                  area: Math.round(area),
                });
              }
            }
          }

          return {
            documentOverflow,
            offscreenControls,
            overlaps,
            hasFrameworkOverlay: Boolean(document.querySelector('vite-error-overlay')),
          };
        });

        expect(
          audit,
          `${viewportName} ${routeName} visual containment audit`,
        ).toEqual({
          documentOverflow: expect.any(Number),
          offscreenControls: [],
          overlaps: [],
          hasFrameworkOverlay: false,
        });
        expect(audit.documentOverflow).toBeLessThanOrEqual(2);
        expect(browserIssues, `${viewportName} ${routeName} console/page errors`).toEqual([]);
      }
    }
  });
});
