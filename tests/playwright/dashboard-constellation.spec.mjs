import { expect, test } from '@playwright/test';
import { PNG } from 'pngjs';

test.describe('usage constellation', () => {
  test('renders nonblank responsive 3D evidence and opens a plotted call', async ({ page }, testInfo) => {
    const mobile = testInfo.project.name === 'chromium-mobile';
    await page.setViewportSize(mobile ? { width: 390, height: 844 } : { width: 1600, height: 900 });
    if (mobile) await page.emulateMedia({ reducedMotion: 'reduce' });
    const browserIssues = collectBrowserIssues(page);

    await page.goto('/?view=overview&qa=r11-usage-constellation');
    await expect(page.getByRole('heading', { name: 'Overview', exact: true })).toBeVisible();
    const section = page.getByTestId('usage-constellation');
    await section.scrollIntoViewIfNeeded();
    await expect(section).toBeVisible();
    if (mobile) {
      expect(await section.evaluate(element => element.getAnimations({ subtree: true }).length)).toBe(0);
    }

    let canvas = page.getByTestId('usage-constellation-canvas');
    await expect(canvas).toHaveAttribute('data-rendered', 'true');
    await expect(canvas).toHaveAttribute('data-point-count', '8');
    const before = await canvas.screenshot({ animations: 'disabled' });
    const pixels = pixelStats(before);
    expect(pixels.nonBackground, 'constellation must render data pixels').toBeGreaterThan(1_000);
    expect(pixels.colorBuckets, 'constellation must contain meaningful color variation').toBeGreaterThan(20);

    const canvasBox = await canvas.boundingBox();
    expect(canvasBox).not.toBeNull();
    await page.mouse.move(canvasBox.x + (canvasBox.width * 0.55), canvasBox.y + (canvasBox.height * 0.55));
    await page.mouse.down();
    await page.mouse.move(canvasBox.x + (canvasBox.width * 0.7), canvasBox.y + (canvasBox.height * 0.48), { steps: 8 });
    await page.mouse.up();
    const rotated = await canvas.screenshot({ animations: 'disabled' });
    expect(pixelDifference(before, rotated), 'dragging must move the 3D camera').toBeGreaterThan(1_000);

    await page.getByRole('button', { name: 'Evidence table', exact: true }).click();
    const tableRegion = page.getByRole('region', { name: 'Usage constellation evidence', exact: true });
    await expect(tableRegion).toBeVisible();
    const tableContract = await tableRegion.evaluate(element => ({
      canScroll: element.scrollWidth > element.clientWidth,
      stickyHeader: getComputedStyle(element.querySelector('thead th')).position,
      openCallButtons: element.querySelectorAll('tbody button').length,
    }));
    expect(tableContract.stickyHeader).toBe('sticky');
    expect(tableContract.openCallButtons).toBe(8);
    if (mobile) expect(tableContract.canScroll).toBe(true);

    await page.getByRole('button', { name: 'Constellation', exact: true }).click();
    canvas = page.getByTestId('usage-constellation-canvas');
    await expect(canvas).toHaveAttribute('data-rendered', 'true');
    const hit = await canvas.evaluate(element => {
      const rect = element.getBoundingClientRect();
      return {
        x: rect.left + Number(element.dataset.primaryHitX),
        y: rect.top + Number(element.dataset.primaryHitY),
      };
    });
    await page.mouse.click(hit.x, hit.y);
    await expect(page).toHaveURL(/view=call/);
    await expect(page).toHaveURL(/record=fixture-call-/);
    await expect(page.getByRole('heading', { name: 'Call Investigator', exact: true })).toBeVisible();

    expect(browserIssues).toEqual([]);
    await testInfo.attach(`usage-constellation-${mobile ? 'mobile' : 'desktop'}.png`, {
      body: before,
      contentType: 'image/png',
    });
  });

  test('falls back to the synchronized table when WebGL is unavailable', async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== 'chromium-desktop', 'One browser project owns capability fallback coverage.');
    await page.addInitScript(() => {
      const getContext = HTMLCanvasElement.prototype.getContext;
      HTMLCanvasElement.prototype.getContext = function patchedGetContext(type, ...args) {
        if (String(type).startsWith('webgl')) return null;
        return getContext.call(this, type, ...args);
      };
    });
    await page.goto('/?view=overview&qa=r11-usage-constellation-no-webgl');
    const section = page.getByTestId('usage-constellation');
    await section.scrollIntoViewIfNeeded();
    await expect(page.getByRole('region', { name: 'Usage constellation evidence', exact: true })).toBeVisible();
    await expect(section).toContainText('3D rendering is unavailable');
    await expect(page.getByRole('button', { name: 'Constellation', exact: true })).toBeDisabled();
  });
});

function pixelStats(buffer) {
  const png = PNG.sync.read(buffer);
  const buckets = new Set();
  let nonBackground = 0;
  for (let index = 0; index < png.data.length; index += 4) {
    const red = png.data[index];
    const green = png.data[index + 1];
    const blue = png.data[index + 2];
    const alpha = png.data[index + 3];
    if (alpha < 8) continue;
    const distance = Math.abs(red - 11) + Math.abs(green - 16) + Math.abs(blue - 22);
    if (distance > 28) nonBackground += 1;
    buckets.add(`${red >> 4}:${green >> 4}:${blue >> 4}`);
  }
  return { colorBuckets: buckets.size, nonBackground };
}

function pixelDifference(leftBuffer, rightBuffer) {
  const left = PNG.sync.read(leftBuffer);
  const right = PNG.sync.read(rightBuffer);
  expect([right.width, right.height]).toEqual([left.width, left.height]);
  let changed = 0;
  for (let index = 0; index < left.data.length; index += 4) {
    const distance = Math.abs(left.data[index] - right.data[index])
      + Math.abs(left.data[index + 1] - right.data[index + 1])
      + Math.abs(left.data[index + 2] - right.data[index + 2]);
    if (distance > 36) changed += 1;
  }
  return changed;
}

function collectBrowserIssues(page) {
  const issues = [];
  page.on('console', message => {
    const text = message.text();
    const expectedPixelReadbackWarning = text.includes('GL Driver Message') && text.includes('ReadPixels');
    if (!expectedPixelReadbackWarning && (message.type() === 'error' || message.type() === 'warning')) {
      issues.push(`${message.type()}: ${text}`);
    }
  });
  page.on('pageerror', error => issues.push(`pageerror: ${error.message}`));
  return issues;
}
