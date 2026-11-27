import { fileURLToPath } from 'node:url';

import { expect, test, type Page } from '@playwright/test';

// Anchored to this file so the output lands in the repo whatever the working directory.
const OUT = fileURLToPath(new URL('../../../docs/screenshots', import.meta.url));
const AUTH = { Authorization: `Bearer ${process.env.VITE_DEMO_TOKEN ?? 'demo-token'}` };
const LAYERS = ['wind', 'gust', 'wave_height', 'wave_period', 'swell', 'current'] as const;
const VIEW = 'view=63.72,8.6,8.3';

interface Manifest {
  layers: Record<
    string,
    { start: string; end: string; segments: { start: string; end: string; source: string }[] }
  >;
}

let manifest: Manifest;
const HOUR = 3600_000;

test.beforeAll(async ({ request }) => {
  const res = await request.get('/weather-data/manifest.json', { headers: AUTH });
  expect(res.ok(), 'run `make pipeline` first').toBeTruthy();
  manifest = await res.json();
});

/** A time a few hours into the first (regional) segment of a layer. */
function regionalTime(layer: string): string {
  const t = Date.parse(manifest.layers[layer]!.segments[0]!.start) + 6 * HOUR;
  return new Date(Math.max(t, Math.floor(Date.now() / HOUR) * HOUR)).toISOString();
}

async function open(page: Page, query: string) {
  const errors: string[] = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
  });
  await page.goto(`/?${query}`, { waitUntil: 'networkidle' });
  await expect(page.locator('.wl-status')).toBeVisible();
  await page.waitForTimeout(2500); // tiles decode + a few particle frames
  return errors;
}

for (const layer of LAYERS) {
  for (const theme of ['light', 'dark'] as const) {
    for (const particles of [0, 1] as const) {
      test(`${layer} ${theme} particles=${particles}`, async ({ page }) => {
        const errors = await open(
          page,
          `layer=${layer}&theme=${theme}&particles=${particles}&thresholds=1&time=${regionalTime(layer)}&${VIEW}`,
        );
        await expect(page.locator('.wl-status .wl-model')).toBeVisible();
        await page.screenshot({
          path: `${OUT}/${layer}-${theme}-${particles ? 'particles' : 'static'}.jpg`,
          type: 'jpeg',
          quality: 78,
        });
        expect(errors).toEqual([]);
      });
    }
  }
}

test('point panel with chart and first exceedance', async ({ page }) => {
  const errors = await open(
    page,
    `layer=wave_height&particles=0&time=${regionalTime('wave_height')}&${VIEW}&panel=63.8,8.3`,
  );
  await expect(page.locator('.wl-point .wl-chart')).toBeVisible();
  await expect(page.locator('.wl-exceed li')).toHaveCount(3);
  await page.screenshot({ path: `${OUT}/point-panel-light.jpg`, type: 'jpeg', quality: 78 });
  expect(errors).toEqual([]);
});

test('ECMWF segment (day 5) zoomed out, dark', async ({ page }) => {
  const seg = manifest.layers.wind!.segments.find((s) => s.source === 'ecmwf')!;
  const t = new Date(Date.parse(seg.start) + 24 * HOUR).toISOString();
  await open(page, `layer=wind&theme=dark&particles=0&time=${t}&view=63.7,8.7,6`);
  await expect(page.locator('.wl-status .wl-model')).toContainText('ECMWF');
  await page.screenshot({ path: `${OUT}/wind-ecmwf-day5-dark.jpg`, type: 'jpeg', quality: 78 });
});

test('time beyond a layer horizon shows a clear message', async ({ page }) => {
  const end = Date.parse(manifest.layers.current!.end);
  const t = new Date(end + 30 * HOUR).toISOString();
  await open(page, `layer=current&particles=0&time=${t}&${VIEW}`);
  await expect(page.locator('.wl-status .wl-warning')).toContainText('Ingen data');
  await page.screenshot({ path: `${OUT}/beyond-horizon-current.jpg`, type: 'jpeg', quality: 78 });
});

test.describe('mobile 390 px', () => {
  test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  test('waves with point panel, light', async ({ page }) => {
    const errors = await open(
      page,
      `layer=wave_height&particles=0&time=${regionalTime('wave_height')}&view=63.75,8.5,7.3&panel=63.8,8.3`,
    );
    await expect(page.locator('.wl-point')).toBeVisible();
    await page.screenshot({ path: `${OUT}/mobile-waves-panel.jpg`, type: 'jpeg', quality: 78 });
    expect(errors).toEqual([]);
  });
  test('wind, dark, particles', async ({ page }) => {
    await open(
      page,
      `layer=wind&theme=dark&particles=1&time=${regionalTime('wind')}&view=63.75,8.5,7.3`,
    );
    await page.screenshot({ path: `${OUT}/mobile-wind-dark.jpg`, type: 'jpeg', quality: 78 });
  });
});
