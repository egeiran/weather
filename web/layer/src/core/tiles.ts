import type { Availability, BBox, Segment } from './types';

export interface TileId {
  z: number;
  x: number;
  y: number;
}

export function lonToMercX(lon: number): number {
  return (lon + 180) / 360;
}

export function latToMercY(lat: number): number {
  const c = Math.max(-85.0511287798, Math.min(85.0511287798, lat));
  const s = Math.sin((c * Math.PI) / 180);
  return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
}

export function mercYToLat(y: number): number {
  return (Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI;
}

/**
 * Data tile zoom for a MapLibre zoom. MapLibre zoom Z draws a 512*2^Z px world; a 256-px tile
 * at zoom Z is shown at 2x (each data pixel ~2 CSS px), which bilinear interpolation handles
 * well and keeps bandwidth low. `offset` > 0 asks for sharper (larger) tiles.
 */
export function tileZoomFor(
  mapZoom: number,
  seg: Pick<Segment, 'minzoom' | 'maxzoom'>,
  offset = 0,
) {
  const z = Math.floor(mapZoom + offset + 1e-6);
  return Math.max(seg.minzoom, Math.min(seg.maxzoom, z));
}

export function decodeBits(av: Availability): Uint8Array {
  const bin = atob(av.bits);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

export class AvailabilityMask {
  private bits: Uint8Array;
  constructor(private av: Availability) {
    this.bits = decodeBits(av);
  }
  has(x: number, y: number): boolean {
    const { x0, y0, width, height } = this.av;
    if (x < x0 || y < y0 || x >= x0 + width || y >= y0 + height) return false;
    const i = (y - y0) * width + (x - x0);
    return ((this.bits[i >> 3] ?? 0) & (1 << (i & 7))) !== 0;
  }
}

const masks = new WeakMap<Availability, AvailabilityMask>();
export function maskFor(av: Availability): AvailabilityMask {
  let m = masks.get(av);
  if (!m) {
    m = new AvailabilityMask(av);
    masks.set(av, m);
  }
  return m;
}

/** Tiles at zoom z intersecting `view` and the segment's bounds that hold data. */
export function visibleTiles(view: BBox, z: number, seg: Segment): TileId[] {
  const b = seg.bounds;
  const west = Math.max(view[0], b[0]);
  const east = Math.min(view[2], b[2]);
  const south = Math.max(view[1], b[1]);
  const north = Math.min(view[3], b[3]);
  if (east <= west || north <= south) return [];
  const n = 2 ** z;
  const x0 = Math.max(0, Math.floor(lonToMercX(west) * n));
  const x1 = Math.min(n - 1, Math.floor(lonToMercX(east) * n - 1e-9));
  const y0 = Math.max(0, Math.floor(latToMercY(north) * n));
  const y1 = Math.min(n - 1, Math.floor(latToMercY(south) * n - 1e-9));
  const av = seg.availability[String(z)];
  const mask = av ? maskFor(av) : null;
  const out: TileId[] = [];
  for (let y = y0; y <= y1; y++) {
    for (let x = x0; x <= x1; x++) {
      if (!mask || mask.has(x, y)) out.push({ z, x, y });
    }
  }
  return out;
}

export function tileUrl(template: string, timeKey: string, t: TileId): string {
  return template
    .replace('{time}', timeKey)
    .replace('{z}', String(t.z))
    .replace('{x}', String(t.x))
    .replace('{y}', String(t.y));
}

export function tileKey(url: string): string {
  return url;
}

/** Mercator [0,1] extent of a tile: [x0, y0, x1, y1]. */
export function tileExtent(t: TileId): [number, number, number, number] {
  const n = 2 ** t.z;
  return [t.x / n, t.y / n, (t.x + 1) / n, (t.y + 1) / n];
}

export function parentTile(t: TileId): TileId | null {
  if (t.z === 0) return null;
  return { z: t.z - 1, x: t.x >> 1, y: t.y >> 1 };
}
