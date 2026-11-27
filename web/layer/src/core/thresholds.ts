/** Threshold logic shared by map marking and the point panel. */

export type ThresholdLayer = 'wave_height' | 'gust' | 'current';

export interface Thresholds {
  wave_height: number | null; // m
  gust: number | null; // m/s
  current: number | null; // kn
}

/** Placeholder defaults (to be set by operations); the UI labels them as such. */
export const DEFAULT_THRESHOLDS: Thresholds = { wave_height: 2.0, gust: 15, current: 1.0 };

/** Series variable that each threshold applies to. */
export const THRESHOLD_VARIABLE: Record<ThresholdLayer, string> = {
  wave_height: 'wave_height',
  gust: 'wind_gust',
  current: 'current_speed',
};

export interface Exceedance {
  layer: ThresholdLayer;
  threshold: number;
  /** First valid time at/after `from` where value > threshold, or null if never. */
  first: Date | null;
  /** True if already above the threshold at `from`. */
  already: boolean;
  /** Last time with data for this variable (exceedance is unknown after it). */
  dataEnd: Date | null;
}

export function firstExceedance(
  times: Date[],
  values: (number | null)[],
  threshold: number,
  from: Date,
): { first: Date | null; already: boolean; dataEnd: Date | null } {
  const t0 = from.getTime();
  // The step in force at `from` is the last valid time <= from (or the first one).
  let start = 0;
  for (let i = 0; i < times.length; i++) if (times[i]!.getTime() <= t0) start = i;
  let first: Date | null = null;
  let dataEnd: Date | null = null;
  for (let i = 0; i < times.length; i++) {
    const v = values[i];
    if (v === null || v === undefined) continue;
    dataEnd = times[i]!;
    if (i >= start && first === null && v > threshold) first = times[i]!;
  }
  const already = first !== null && first.getTime() <= t0;
  return { first: already ? from : first, already, dataEnd };
}

/** Is `value` over the threshold? (Strictly greater, like the map marking.) */
export function exceeds(value: number | null, threshold: number | null): boolean {
  return value !== null && threshold !== null && value > threshold;
}
