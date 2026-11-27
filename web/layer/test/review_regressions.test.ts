/** Regression tests for findings of the independent review (docs/PROGRESS.md). */
import { availableLayers } from '../src/core/manifest';
import { firstExceedance } from '../src/core/thresholds';
import { resolveTime } from '../src/core/time';
import { TileStore } from '../src/core/tileStore';
import type { Manifest } from '../src/core/types';
import { windLayer } from './fixtures';

test('no hole between MEPS (hourly) and ECMWF (3-hourly)', () => {
  const layer = windLayer(); // MEPS ends 2026-11-30T00Z, ECMWF starts 03Z
  expect(resolveTime(layer, new Date('2026-11-30T01:00:00Z'))!.time.toISOString()).toBe(
    '2026-11-30T00:00:00.000Z',
  );
  const r = resolveTime(layer, new Date('2026-11-30T02:00:00Z'))!;
  expect(r.segment.source).toBe('ecmwf');
  expect(r.time.toISOString()).toBe('2026-11-30T03:00:00.000Z');
});

test('first exceedance uses the variable’s own step in force (union axis has gaps)', () => {
  // Union axis hourly (because of other variables); gust only every 3 h.
  const times = ['12', '13', '14', '15'].map((h) => new Date(`2026-12-01T${h}:00:00Z`));
  const gust = [16, null, null, 10];
  const from = new Date('2026-12-01T13:00:00Z');
  const r = firstExceedance(times, gust, 15, from);
  expect(r.already).toBe(true); // the map shows the 12:00 field, which is over 15 m/s
  expect(r.first).toEqual(from);
});

test('a value exactly at the threshold is not an exceedance (strict >, like the map)', () => {
  const times = ['06', '07'].map((h) => new Date(`2026-11-27T${h}:00:00Z`));
  const r = firstExceedance(times, [2.0, 2.0], 2.0, times[0]!);
  expect(r.first).toBeNull();
});

test('unknown layer ids from newer minor versions are ignored', () => {
  const seg = windLayer();
  const m = {
    layers: { wind: seg, visibility: seg, current: { ...seg, segments: [] } },
  } as unknown as Manifest;
  expect(availableLayers(m)).toEqual(['wind']);
});

test('failed tiles are retried with backoff', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('createImageBitmap', async () => ({ close() {} }));
  let calls = 0;
  const fetchFn = async () => {
    calls++;
    return calls === 1
      ? new Response('down', { status: 503 })
      : new Response(new Blob([new Uint8Array(4)]));
  };
  const store = new TileStore(fetchFn, () => {});
  store.request('t.png');
  await vi.runAllTicks();
  await vi.waitFor(() => expect(store.get('t.png')!.state).toBe('error'));
  expect(store.stats.errors).toBe(1);
  store.request('t.png'); // too early: stays failed
  expect(calls).toBe(1);
  vi.advanceTimersByTime(2100);
  store.request('t.png');
  await vi.waitFor(() => expect(store.get('t.png')!.state).toBe('decoded'));
  expect(calls).toBe(2);
  expect(store.stats.errors).toBe(0);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
