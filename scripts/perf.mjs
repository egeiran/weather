// Measure the performance budget in a real (GPU) headless Chromium.
// Usage: node scripts/perf.mjs <baseUrl> <label> [scenario...]
//   scenario = name|query   (query appended to the demo URL)
// Prints a Markdown table: first-view bytes, time-step-change bytes, click bytes/requests, fps.
import { chromium } from '@playwright/test';

const [, , base = 'http://localhost:5173', label = 'dev', ...scenarios] = process.argv;
const GPU_ARGS = ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'];

async function measure(browser, name, query) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  let bytes = 0;
  let requests = 0;
  const seriesRequests = [];
  page.on('response', async (res) => {
    const url = res.url();
    if (!url.includes('/weather-data/')) return;
    try {
      const body = await res.body();
      bytes += body.length;
      requests++;
      if (url.includes('/series/')) seriesRequests.push(body.length);
    } catch {
      /* aborted */
    }
  });
  const settle = async () => {
    await page.waitForLoadState('networkidle');
    await page.waitForFunction(() => !document.querySelector('.wl-spinner'), null, { timeout: 30000 });
    await page.waitForTimeout(400);
  };
  const t0 = Date.now();
  await page.goto(`${base}/?${query}`, { waitUntil: 'domcontentloaded' });
  await settle();
  const firstMs = Date.now() - t0;
  const first = { bytes, requests };
  // three time-step changes (prefetch of the next step happens in the background, so we count
  // everything fetched between two settled states)
  const steps = [];
  for (let i = 0; i < 3; i++) {
    const b0 = bytes;
    const r0 = requests;
    await page.getByRole('button', { name: /Neste tidssteg|Next time step/ }).click();
    await settle();
    steps.push({ bytes: bytes - b0, requests: requests - r0 });
  }
  // a click for values
  const c0 = seriesRequests.length;
  const b1 = bytes;
  const r1 = requests;
  await page.mouse.click(720, 420);
  await page.waitForSelector('.wl-point .wl-values, .wl-point .wl-muted', { timeout: 15000 });
  await page.waitForTimeout(500);
  const click = { bytes: bytes - b1, requests: requests - r1, series: seriesRequests.length - c0 };
  // fps with particles over 5 s
  const fps = await page.evaluate(
    () =>
      new Promise((resolve) => {
        let n = 0;
        const start = performance.now();
        const loop = (t) => {
          n++;
          if (t - start < 5000) requestAnimationFrame(loop);
          else resolve(Math.round((n * 1000) / (t - start)));
        };
        requestAnimationFrame(loop);
      }),
  );
  const renderer = await page.evaluate(() => {
    const gl = document.createElement('canvas').getContext('webgl2');
    const ext = gl?.getExtension('WEBGL_debug_renderer_info');
    return gl ? gl.getParameter(ext ? ext.UNMASKED_RENDERER_WEBGL : gl.RENDERER) : 'none';
  });
  await page.close();
  return { name, firstMs, first, steps, click, fps, renderer };
}

const browser = await chromium.launch({ args: GPU_ARGS });
const rows = [];
for (const s of scenarios) {
  const [name, query] = s.split('|');
  rows.push(await measure(browser, name, query));
}
await browser.close();

const kb = (b) => `${(b / 1024).toFixed(0)} KB`;
console.log(`\n### ${label} (1440×900 @2x, ${rows[0]?.renderer})\n`);
console.log('| scenario | first view | step change (avg of 3) | click | fps (particles) |');
console.log('|---|---|---|---|---:|');
for (const r of rows) {
  const avg = r.steps.reduce((a, s) => a + s.bytes, 0) / r.steps.length;
  const avgReq = r.steps.reduce((a, s) => a + s.requests, 0) / r.steps.length;
  console.log(
    `| ${r.name} | ${kb(r.first.bytes)} in ${r.first.requests} req, ${(r.firstMs / 1000).toFixed(1)} s | ` +
      `${kb(avg)} in ${avgReq.toFixed(1)} req | ${kb(r.click.bytes)} in ${r.click.requests} req ` +
      `(${r.click.series} series) | ${r.fps} |`,
  );
}
