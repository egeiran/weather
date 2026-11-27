import type { LayerInfo, Manifest, Segment } from './types';

const HOUR = 3600_000;

export interface ResolvedTime {
  segment: Segment;
  segmentIndex: number;
  /** The valid time actually shown (nearest available step). */
  time: Date;
  /** Path segment used in tile URLs, e.g. 20261127T0600Z. */
  timeKey: string;
}

export function parseTime(iso: string): Date {
  return new Date(iso);
}

/** "2026-11-27T06:00:00Z" -> "20261127T0600Z" (manifest tile.time_format %Y%m%dT%H%MZ). */
export function timeKey(t: Date | string): string {
  const d = typeof t === 'string' ? new Date(t) : t;
  const p = (n: number) => String(n).padStart(2, '0');
  return (
    `${d.getUTCFullYear()}${p(d.getUTCMonth() + 1)}${p(d.getUTCDate())}` +
    `T${p(d.getUTCHours())}${p(d.getUTCMinutes())}Z`
  );
}

function nearestIndex(times: number[], t: number): number {
  let lo = 0;
  let hi = times.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (times[mid]! <= t) lo = mid;
    else hi = mid;
  }
  return Math.abs(times[lo]! - t) <= Math.abs(times[hi]! - t) ? lo : hi;
}

/**
 * Pick the segment and nearest valid time for `t`. Between two segments (e.g. the last MEPS
 * hour and the first ECMWF 3-hourly step) the nearer boundary time wins, so a stitched layer has
 * no holes. Returns null only when `t` is more than half a step before the layer's first time
 * or after its last time.
 */
export function resolveTime(layer: LayerInfo, t: Date): ResolvedTime | null {
  const target = t.getTime();
  const all: { ms: number; iso: string; seg: Segment; i: number }[] = [];
  layer.segments.forEach((seg, i) => {
    for (const iso of seg.times) all.push({ ms: Date.parse(iso), iso, seg, i });
  });
  if (!all.length) return null;
  all.sort((a, b) => a.ms - b.ms);
  const first = all[0]!;
  const last = all[all.length - 1]!;
  const tolStart = ((first.seg.step_hours ?? 1) * HOUR) / 2 + 1;
  const tolEnd = ((last.seg.step_hours ?? 1) * HOUR) / 2 + 1;
  if (target < first.ms - tolStart || target > last.ms + tolEnd) return null;
  const idx = nearestIndex(
    all.map((x) => x.ms),
    target,
  );
  const hit = all[idx]!;
  return {
    segment: hit.seg,
    segmentIndex: hit.i,
    time: new Date(hit.iso),
    timeKey: timeKey(hit.iso),
  };
}

export interface TimeRange {
  start: Date;
  end: Date;
}

export function layerRange(layer: LayerInfo): TimeRange {
  return { start: new Date(layer.start), end: new Date(layer.end) };
}

/** Union range over all layers (the timeline the host should offer). */
export function manifestRange(m: Manifest): TimeRange | null {
  let start = Infinity;
  let end = -Infinity;
  for (const layer of Object.values(m.layers)) {
    if (!layer) continue;
    start = Math.min(start, Date.parse(layer.start));
    end = Math.max(end, Date.parse(layer.end));
  }
  return Number.isFinite(start) ? { start: new Date(start), end: new Date(end) } : null;
}

/** All valid times of a layer, across segments (sorted). */
export function layerTimes(layer: LayerInfo): Date[] {
  return layer.segments.flatMap((s) => s.times.map((t) => new Date(t)));
}

/** Next/previous available time of the layer relative to t (for stepping and playback). */
export function stepTime(layer: LayerInfo, t: Date, dir: 1 | -1): Date | null {
  const times = layerTimes(layer).map((d) => d.getTime());
  const x = t.getTime();
  if (dir > 0) {
    const n = times.find((v) => v > x + 1);
    return n === undefined ? null : new Date(n);
  }
  const p = [...times].reverse().find((v) => v < x - 1);
  return p === undefined ? null : new Date(p);
}

/** Floor a date to the whole hour (UTC). */
export function floorHour(d: Date): Date {
  return new Date(Math.floor(d.getTime() / HOUR) * HOUR);
}
