/**
 * Colour ramps. A ramp = value stops of the layer (non-linear, finer where it matters) paired
 * with colours sampled evenly from a continuous colormap. All colormaps here are sequential
 * with monotonic lightness, so they never rely on a red/green distinction (colour-blind safe).
 * Ramps are rendered into a 256x1 texture on the client: changing a ramp needs no new tiles.
 */
import type { LayerId } from './types';

export type RampFamily = 'calm' | 'vivid' | 'viridis';
export const RAMP_FAMILIES: RampFamily[] = ['calm', 'vivid', 'viridis'];

type Kind = 'wind' | 'wave' | 'period' | 'current';

const KIND: Record<LayerId, Kind> = {
  wind: 'wind',
  gust: 'wind',
  wave_height: 'wave',
  swell: 'wave',
  wave_period: 'period',
  current: 'current',
};

/** Value stops per layer (also the legend ticks). Units: m/s, m, s, kn. */
export const VALUE_STOPS: Record<LayerId, number[]> = {
  wind: [0, 2, 4, 6, 8, 10, 12, 15, 18, 21, 25, 30],
  gust: [0, 3, 6, 9, 12, 15, 18, 21, 25, 30, 35, 40],
  wave_height: [0, 0.25, 0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8],
  wave_period: [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22],
  swell: [0, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4, 5, 6],
  current: [0, 0.1, 0.2, 0.3, 0.5, 0.7, 1, 1.25, 1.5, 2, 2.5, 3],
};

interface FamilyDef {
  maps: Record<Kind, string[]>;
  alpha: [number, number]; // opacity at the low and high end of the ramp
}

const FAMILIES: Record<RampFamily, FamilyDef> = {
  // Quiet, translucent at low values so the basemap and vessels stay readable.
  calm: {
    maps: {
      wind: [
        '#eef4f9',
        '#c9ddef',
        '#93c0e0',
        '#5f9fd0',
        '#3b7cbd',
        '#3b5aa8',
        '#56419a',
        '#77308c',
        '#93246f',
        '#6d1a4d',
      ],
      wave: [
        '#effaf7',
        '#c4ebe4',
        '#8fd4d3',
        '#5cb7c8',
        '#3a94bb',
        '#2e70a8',
        '#334f95',
        '#4a3485',
        '#6b2178',
        '#511556',
      ],
      period: [
        '#f5f2fa',
        '#ddd6ec',
        '#bfb5dc',
        '#9d93ca',
        '#7e73b8',
        '#6455a5',
        '#4f3b8e',
        '#3d2677',
        '#2c1761',
        '#1d0c48',
      ],
      current: [
        '#fbf6e9',
        '#ece9c4',
        '#cfe0a6',
        '#a6cf93',
        '#78ba88',
        '#4fa184',
        '#33857d',
        '#226872',
        '#1b4c61',
        '#14324a',
      ],
    },
    alpha: [0.3, 0.82],
  },
  // Windy-like multi-hue (Crameri "batlow"-style): stronger, still colour-blind safe.
  vivid: {
    maps: {
      wind: [
        '#0d1a5a',
        '#163f6a',
        '#1d5e6e',
        '#3a7663',
        '#678449',
        '#9d8c34',
        '#d4904f',
        '#f39b84',
        '#fbb7c2',
        '#fcd7f5',
      ],
      wave: [
        '#0d1a5a',
        '#163f6a',
        '#1d5e6e',
        '#3a7663',
        '#678449',
        '#9d8c34',
        '#d4904f',
        '#f39b84',
        '#fbb7c2',
        '#fcd7f5',
      ],
      period: [
        '#1a0d40',
        '#3b1764',
        '#5f2181',
        '#842c8f',
        '#a83c8e',
        '#c9547f',
        '#e17468',
        '#ef9a58',
        '#f6c35a',
        '#f9ec7d',
      ],
      current: [
        '#0d1a5a',
        '#163f6a',
        '#1d5e6e',
        '#3a7663',
        '#678449',
        '#9d8c34',
        '#d4904f',
        '#f39b84',
        '#fbb7c2',
        '#fcd7f5',
      ],
    },
    alpha: [0.62, 0.85],
  },
  // Perceptually uniform matplotlib maps (viridis / cividis / mako-like).
  viridis: {
    maps: {
      wind: [
        '#440154',
        '#482878',
        '#3e4a89',
        '#31688e',
        '#26828e',
        '#1f9e89',
        '#35b779',
        '#6ece58',
        '#b5de2b',
        '#fde725',
      ],
      wave: [
        '#00224e',
        '#123570',
        '#3b496c',
        '#575d6d',
        '#707173',
        '#8a8678',
        '#a59c74',
        '#c3b369',
        '#e1cc55',
        '#fee838',
      ],
      period: [
        '#0b0405',
        '#2b1b3f',
        '#3c3171',
        '#3e4e8f',
        '#38709b',
        '#3490a1',
        '#40afa5',
        '#6acba3',
        '#a8e0b4',
        '#def5e5',
      ],
      current: [
        '#0b0405',
        '#2b1b3f',
        '#3c3171',
        '#3e4e8f',
        '#38709b',
        '#3490a1',
        '#40afa5',
        '#6acba3',
        '#a8e0b4',
        '#def5e5',
      ],
    },
    alpha: [0.6, 0.8],
  },
};

// --- colour maths (OKLab interpolation for even perceptual steps) -------------------------

type RGB = [number, number, number];

export function hexToRgb(hex: string): RGB {
  const h = hex.replace('#', '');
  return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255) as RGB;
}

const toLin = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const toSrgb = (c: number) => (c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055);

function rgbToOklab([r, g, b]: RGB): RGB {
  const [lr, lg, lb] = [toLin(r), toLin(g), toLin(b)];
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  return [
    0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s,
    1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s,
    0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s,
  ];
}

function oklabToRgb([L, a, b]: RGB): RGB {
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const rgb = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  return rgb.map((c) => Math.min(1, Math.max(0, toSrgb(c)))) as RGB;
}

/** Sample a list of hex anchors at t in [0,1] (OKLab interpolation). */
export function sampleColormap(anchors: string[], t: number): RGB {
  const x = Math.min(1, Math.max(0, t)) * (anchors.length - 1);
  const i = Math.min(anchors.length - 2, Math.floor(x));
  const f = x - i;
  const a = rgbToOklab(hexToRgb(anchors[i]!));
  const b = rgbToOklab(hexToRgb(anchors[i + 1]!));
  return oklabToRgb([a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f]);
}

export interface RampStop {
  value: number;
  color: RGB; // 0..1 sRGB
  alpha: number;
}

export interface Ramp {
  layer: LayerId;
  family: RampFamily;
  min: number;
  max: number;
  stops: RampStop[];
}

export function getRamp(layer: LayerId, family: RampFamily = 'calm'): Ramp {
  const values = VALUE_STOPS[layer];
  const def = FAMILIES[family];
  const anchors = def.maps[KIND[layer]];
  const n = values.length;
  const stops = values.map((value, i) => {
    const t = i / (n - 1);
    return {
      value,
      color: sampleColormap(anchors, t),
      alpha: def.alpha[0] + (def.alpha[1] - def.alpha[0]) * Math.sqrt(t),
    };
  });
  return { layer, family, min: values[0]!, max: values[n - 1]!, stops };
}

/** Colour of a value on the ramp (piecewise linear between stops, clamped). */
export function rampColor(ramp: Ramp, value: number): { color: RGB; alpha: number } {
  const s = ramp.stops;
  if (value <= s[0]!.value) return { color: s[0]!.color, alpha: s[0]!.alpha };
  for (let i = 1; i < s.length; i++) {
    const b = s[i]!;
    if (value <= b.value) {
      const a = s[i - 1]!;
      const f = (value - a.value) / (b.value - a.value);
      const la = rgbToOklab(a.color);
      const lb = rgbToOklab(b.color);
      return {
        color: oklabToRgb([
          la[0] + (lb[0] - la[0]) * f,
          la[1] + (lb[1] - la[1]) * f,
          la[2] + (lb[2] - la[2]) * f,
        ]),
        alpha: a.alpha + (b.alpha - a.alpha) * f,
      };
    }
  }
  const last = s[s.length - 1]!;
  return { color: last.color, alpha: last.alpha };
}

/** 256x1 RGBA (straight alpha) lookup table over [min, max], linear in value. */
export function rampTexels(ramp: Ramp, size = 256): Uint8Array {
  const out = new Uint8Array(size * 4);
  for (let i = 0; i < size; i++) {
    const v = ramp.min + ((ramp.max - ramp.min) * i) / (size - 1);
    const { color, alpha } = rampColor(ramp, v);
    out[i * 4] = Math.round(color[0] * 255);
    out[i * 4 + 1] = Math.round(color[1] * 255);
    out[i * 4 + 2] = Math.round(color[2] * 255);
    out[i * 4 + 3] = Math.round(alpha * 255);
  }
  return out;
}

export function cssColor(c: RGB, alpha = 1): string {
  const [r, g, b] = c.map((x) => Math.round(x * 255));
  return alpha >= 1 ? `rgb(${r} ${g} ${b})` : `rgb(${r} ${g} ${b} / ${alpha.toFixed(2)})`;
}

/** CSS linear-gradient for legends (positions proportional to value). */
export function cssGradient(ramp: Ramp, opaque = true): string {
  const span = ramp.max - ramp.min;
  const parts = ramp.stops.map(
    (s) =>
      `${cssColor(s.color, opaque ? 1 : s.alpha)} ${(((s.value - ramp.min) / span) * 100).toFixed(1)}%`,
  );
  return `linear-gradient(to right, ${parts.join(', ')})`;
}

/** Relative luminance (for picking legible text/arrow colours over a ramp). */
export function luminance([r, g, b]: RGB): number {
  return 0.2126 * toLin(r) + 0.7152 * toLin(g) + 0.0722 * toLin(b);
}
