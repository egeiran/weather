/**
 * CPU reference of the value decoding done in the shaders (FIELD_FS / VECTOR_FS). Used by tests
 * and available to hosts that want a value under the cursor from an already decoded tile.
 */
import type { Channel } from './types';

export const NODATA = 255;

export function decodeCode(ch: Pick<Channel, 'scale' | 'offset'>, code: number): number | null {
  return code === NODATA ? null : ch.offset + ch.scale * code;
}

/**
 * Bilinear sample of one channel of a buffered tile (RGBA bytes, size x size incl. border) at
 * tile-local uv (0..1, y down). No-data taps are dropped and weights renormalised; returns null
 * when less than half of the weight is valid (same rule as the pipeline and the shader).
 */
export function sampleTile(
  rgba: Uint8Array | Uint8ClampedArray,
  size: number,
  uv: [number, number],
  channel: number,
  ch: Pick<Channel, 'scale' | 'offset'>,
): number | null {
  const inner = size - 2;
  const px = uv[0] * inner + 0.5;
  const py = uv[1] * inner + 0.5;
  const x0 = Math.floor(px);
  const y0 = Math.floor(py);
  const fx = px - x0;
  const fy = py - y0;
  let sum = 0;
  let wsum = 0;
  for (let dy = 0; dy < 2; dy++) {
    for (let dx = 0; dx < 2; dx++) {
      const x = Math.min(size - 1, Math.max(0, x0 + dx));
      const y = Math.min(size - 1, Math.max(0, y0 + dy));
      const code = rgba[(y * size + x) * 4 + channel]!;
      const w = (dx ? fx : 1 - fx) * (dy ? fy : 1 - fy);
      if (code !== NODATA) {
        sum += w * (ch.offset + ch.scale * code);
        wsum += w;
      }
    }
  }
  return wsum < 0.5 ? null : sum / wsum;
}

/** Motion vector (east, north) from speed and a direction in the given convention. */
export function motionVector(
  speed: number,
  directionDeg: number,
  convention: 'from' | 'to',
): [number, number] {
  const rad = ((directionDeg + (convention === 'from' ? 180 : 0)) * Math.PI) / 180;
  return [speed * Math.sin(rad), speed * Math.cos(rad)];
}
