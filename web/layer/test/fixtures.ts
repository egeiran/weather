import type { LayerInfo, Segment } from '../src/core/types';

const H = 3600_000;

export function times(startIso: string, stepH: number, n: number): string[] {
  const t0 = Date.parse(startIso);
  return Array.from({ length: n }, (_, i) =>
    new Date(t0 + i * stepH * H).toISOString().replace('.000Z', 'Z'),
  );
}

export function segment(source: string, ts: string[], step: number): Segment {
  return {
    source,
    run_id: '20261127T06Z',
    label: `${source.toUpperCase()} 06Z`,
    start: ts[0]!,
    end: ts[ts.length - 1]!,
    step_hours: step,
    times: ts,
    tiles: `runs/${source}/20261127T06Z/wind/{time}/{z}/{x}/{y}.png`,
    minzoom: 2,
    maxzoom: 5,
    bounds: [7.5, 63.2, 10, 64.2],
    availability: {},
    channels: [
      { name: 'wind_speed', unit: 'm/s', scale: 0.2, offset: 0, nodata: 255, min: 0, max: 50.8 },
      {
        name: 'wind_from_direction',
        unit: 'deg',
        scale: 360 / 255,
        offset: 0,
        nodata: 255,
        min: 0,
        max: 358.6,
        wrap: 360,
      },
      { name: 'wind_gust', unit: 'm/s', scale: 0.25, offset: 0, nodata: 255, min: 0, max: 63.5 },
    ],
    value_channel: 0,
    direction_channel: 1,
  };
}

/** MEPS hourly 06Z+0..66 h, then ECMWF 3-hourly and 6-hourly (as the pipeline stitches). */
export function windLayer(): LayerInfo {
  const meps = times('2026-11-27T06:00:00Z', 1, 67);
  const ec3 = times('2026-11-30T03:00:00Z', 3, 23);
  const ec6 = times('2026-12-03T06:00:00Z', 6, 16);
  const segs = [segment('meps', meps, 1), segment('ecmwf', ec3, 3), segment('ecmwf', ec6, 6)];
  return {
    product: 'wind',
    unit: 'm/s',
    value: 'wind_speed',
    direction: 'wind_from_direction',
    direction_convention: 'from',
    particles: true,
    start: segs[0]!.start,
    end: segs[2]!.end,
    segments: segs,
  };
}
