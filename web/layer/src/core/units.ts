/** Formatting of values, directions and times. */

export function formatValue(v: number | null | undefined, unit: string, locale: string): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '–';
  const digits = unit === 'm/s' || unit === 's' || unit === 'degC' ? 1 : unit === 'kn' ? 1 : 1;
  const n = new Intl.NumberFormat(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(v);
  return `${n} ${displayUnit(unit)}`;
}

export function displayUnit(unit: string): string {
  return unit === 'degC' ? '°C' : unit === 'deg' ? '°' : unit;
}

/**
 * 16-point compass name of a bearing. `points` are the localised names, N first, clockwise
 * (message key `compass.points`, comma separated).
 */
export function compass(deg: number | null | undefined, points: readonly string[]): string {
  if (deg === null || deg === undefined || !Number.isFinite(deg) || points.length !== 16)
    return '–';
  return points[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16]!;
}

export const DEFAULT_TIME_ZONE = 'Europe/Oslo';

export function formatTime(d: Date, locale: string, timeZone = DEFAULT_TIME_ZONE): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  }).format(d);
}

export function formatShortTime(d: Date, locale: string, timeZone = DEFAULT_TIME_ZONE): string {
  return new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone,
  }).format(d);
}

/** Compact label for chart axes, e.g. "fre. 14" / "Fri 14". */
export function formatAxisTime(d: Date, locale: string, timeZone = DEFAULT_TIME_ZONE): string {
  const parts = new Intl.DateTimeFormat(locale, {
    weekday: 'short',
    hour: '2-digit',
    hourCycle: 'h23',
    timeZone,
  }).formatToParts(d);
  const wd = parts.find((p) => p.type === 'weekday')?.value ?? '';
  const hr = parts.find((p) => p.type === 'hour')?.value ?? '';
  return `${wd} ${hr}`;
}
