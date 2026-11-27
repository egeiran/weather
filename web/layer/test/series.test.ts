import { cellSeries, chunkFor, parseChunk } from '../src/core/series';
import { firstExceedance } from '../src/core/thresholds';
import type { SeriesInfo } from '../src/core/types';
import { valueAt } from '../src/react/PointPanel';

function gzip(data: Uint8Array): Promise<Uint8Array> {
  const s = new Blob([data as BlobPart]).stream().pipeThrough(new CompressionStream('gzip'));
  return new Response(s).arrayBuffer().then((b) => new Uint8Array(b));
}

function chunkBytes(
  nv: number,
  rows: number,
  cols: number,
  nt: number,
  f: (v: number, r: number, c: number, t: number) => number,
) {
  const out = new Uint8Array(12 + nv * rows * cols * nt);
  out.set([0x57, 0x4c, 0x53, 0x31]); // WLS1
  const dv = new DataView(out.buffer);
  dv.setUint16(4, rows, true);
  dv.setUint16(6, cols, true);
  dv.setUint16(8, nv, true);
  dv.setUint16(10, nt, true);
  let i = 12;
  for (let v = 0; v < nv; v++)
    for (let r = 0; r < rows; r++)
      for (let c = 0; c < cols; c++) for (let t = 0; t < nt; t++) out[i++] = f(v, r, c, t);
  return out;
}

const series: SeriesInfo = {
  id: 'x',
  template: 'series/x/{cy}/{cx}.bin',
  format: 'WLS1+gzip',
  grid: {
    origin: [-180, -90],
    dlon: 0.05,
    dlat: 0.025,
    chunk: 4,
    row0: 6124,
    col0: 3748,
    rows: 44,
    cols: 52,
  },
  times: [
    '2026-11-27T06:00:00Z',
    '2026-11-27T07:00:00Z',
    '2026-11-27T08:00:00Z',
    '2026-11-27T09:00:00Z',
  ],
  variables: [
    {
      name: 'wave_height',
      unit: 'm',
      scale: 0.1,
      offset: 0,
      nodata: 255,
      min: 0,
      max: 25.4,
      product: 'waves',
      segments: [],
    },
    {
      name: 'wind_gust',
      unit: 'm/s',
      scale: 0.25,
      offset: 0,
      nodata: 255,
      min: 0,
      max: 63.5,
      product: 'wind',
      segments: [],
    },
  ],
  // all chunks of the window present
  availability: {
    x0: 937,
    y0: 1531,
    width: 13,
    height: 11,
    count: 143,
    bits: btoa(String.fromCharCode(...new Array(18).fill(255))),
  },
};

describe('point series', () => {
  test('chunk lookup from lon/lat', () => {
    const ref = chunkFor(series, 8.5, 63.7)!;
    expect(ref.cy).toBe(Math.floor((63.7 + 90) / 0.1));
    expect(ref.cx).toBe(Math.floor((8.5 + 180) / 0.2));
    expect(ref.row).toBe(Math.floor((63.7 + 90) / 0.025) - ref.cy * 4);
    expect(Math.abs(ref.cellLat - 63.7)).toBeLessThan(0.0125 + 1e-9);
    expect(chunkFor(series, 30, 70)).toBeNull();
  });

  test('parses gzip and plain chunks; decodes values with no-data', async () => {
    const raw = chunkBytes(2, 4, 4, 4, (v, r, c, t) =>
      v === 0 ? (t === 3 ? 255 : 10 + t * 10) : 40 + t,
    );
    for (const bytes of [raw, await gzip(raw)]) {
      const chunk = await parseChunk(bytes);
      expect([chunk.rows, chunk.cols, chunk.nvars, chunk.ntimes]).toEqual([4, 4, 2, 4]);
      const s = cellSeries(series, chunk, 1, 2);
      expect(s.wave_height![0]).toBeCloseTo(1.0);
      expect(s.wave_height![2]).toBeCloseTo(3.0);
      expect(s.wave_height![3]).toBeNull();
      expect(s.wind_gust![1]).toBeCloseTo(10.25);
    }
  });

  test('rejects garbage', async () => {
    await expect(
      parseChunk(new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12])),
    ).rejects.toThrow();
  });
});

describe('thresholds', () => {
  const ts = ['06', '07', '08', '09', '10'].map((h) => new Date(`2026-11-27T${h}:00:00Z`));

  test('first exceedance after now', () => {
    const r = firstExceedance(
      ts,
      [1.2, 1.8, 2.4, 2.9, null],
      2.0,
      new Date('2026-11-27T06:30:00Z'),
    );
    expect(r.first?.toISOString()).toBe('2026-11-27T08:00:00.000Z');
    expect(r.already).toBe(false);
    expect(r.dataEnd?.toISOString()).toBe('2026-11-27T09:00:00.000Z');
  });

  test('already over now', () => {
    const now = new Date('2026-11-27T08:10:00Z');
    const r = firstExceedance(ts, [1.2, 1.8, 2.4, 2.9, null], 2.0, now);
    expect(r.already).toBe(true);
    expect(r.first).toEqual(now);
  });

  test('never exceeded, and exceedances before now are ignored', () => {
    const r = firstExceedance(ts, [3.0, 1.0, 1.1, 1.2, 1.3], 2.0, new Date('2026-11-27T07:00:00Z'));
    expect(r.first).toBeNull();
    expect(r.dataEnd?.toISOString()).toBe('2026-11-27T10:00:00.000Z');
  });

  test('value lookup picks the nearest step with data', () => {
    expect(valueAt(ts, [1, null, 3, null, null], new Date('2026-11-27T06:40:00Z'))).toBe(1);
    expect(valueAt(ts, [1, null, 3, null, null], new Date('2026-11-27T07:10:00Z'))).toBe(3);
    expect(valueAt(ts, [null, null, null, null, null], ts[0]!)).toBeNull();
  });
});
