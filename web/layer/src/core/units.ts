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

const COMPASS_EN = [
  'N',
  'NNE',
  'NE',
  'ENE',
  'E',
  'ESE',
  'SE',
  'SSE',
  'S',
  'SSW',
  'SW',
  'WSW',
  'W',
  'WNW',
  'NW',
  'NNW',
];
const COMPASS_NB = [
  'N',
  'NNØ',
  'NØ',
  'ØNØ',
  'Ø',
  'ØSØ',
  'SØ',
  'SSØ',
  'S',
  'SSV',
  'SV',
  'VSV',
  'V',
  'VNV',
  'NV',
  'NNV',
];

export function compass(deg: number | null | undefined, locale: string): string {
  if (deg === null || deg === undefined || !Number.isFinite(deg)) return '–';
  const names = locale.startsWith('nb') || locale.startsWith('no') ? COMPASS_NB : COMPASS_EN;
  return names[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16]!;
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
