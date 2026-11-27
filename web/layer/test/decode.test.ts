import { decodeCode, motionVector, sampleTile } from '../src/core/decode';
import { AvailabilityMask, tileZoomFor, visibleTiles } from '../src/core/tiles';
import { segment, times } from './fixtures';

const speed = { scale: 0.2, offset: 0 };

function tile(fill: (x: number, y: number) => number, size = 258): Uint8Array {
  const a = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const i = (y * size + x) * 4;
      a[i] = fill(x, y);
      a[i + 3] = 255;
    }
  return a;
}

describe('tile decoding', () => {
  test('linear decode and no-data', () => {
    expect(decodeCode(speed, 0)).toBe(0);
    expect(decodeCode(speed, 50)).toBeCloseTo(10);
    expect(decodeCode(speed, 255)).toBeNull();
  });

  test('bilinear sampling hits texel centres exactly and interpolates between them', () => {
    const t = tile((x) => x % 255); // code = column index
    // texel j centre is at uv = (j - 0.5) / 256
    expect(sampleTile(t, 258, [(10 - 0.5) / 256, 0.5], 0, speed)).toBeCloseTo(10 * 0.2);
    expect(sampleTile(t, 258, [10 / 256, 0.5], 0, speed)).toBeCloseTo(10.5 * 0.2);
  });

  test('no-data taps are dropped; mostly-no-data is null (coastline rule)', () => {
    const t = tile((x) => (x >= 100 ? 255 : 50));
    const lastSea = (99 - 0.5) / 256;
    expect(sampleTile(t, 258, [lastSea, 0.5], 0, speed)).toBeCloseTo(10);
    expect(sampleTile(t, 258, [lastSea + 0.4 / 256, 0.5], 0, speed)).toBeCloseTo(10); // 60% sea
    expect(sampleTile(t, 258, [lastSea + 0.6 / 256, 0.5], 0, speed)).toBeNull(); // 40% sea
  });

  test('direction conventions give the motion vector', () => {
    const [u, v] = motionVector(10, 270, 'from'); // westerly wind blows towards east
    expect(u).toBeCloseTo(10);
    expect(v).toBeCloseTo(0);
    const [cu, cv] = motionVector(1, 0, 'to'); // current towards north
    expect(cu).toBeCloseTo(0);
    expect(cv).toBeCloseTo(1);
  });
});

describe('tiles', () => {
  test('availability bitset (LSB first, row-major)', () => {
    // bits for (x0=3,y0=5,w=4,h=3), present (3,5),(4,5),(6,7) -> bytes 0b0000_0011, 0b0000_1000
    const bits = btoa(String.fromCharCode(0b00000011, 0b00001000));
    const m = new AvailabilityMask({ x0: 3, y0: 5, width: 4, height: 3, count: 3, bits });
    expect([m.has(3, 5), m.has(4, 5), m.has(6, 7), m.has(5, 6), m.has(2, 5)]).toEqual([
      true,
      true,
      true,
      false,
      false,
    ]);
  });

  test('tile zoom is clamped to the segment', () => {
    const seg = segment('meps', times('2026-11-27T06:00:00Z', 1, 2), 1);
    expect(tileZoomFor(9.7, seg)).toBe(5);
    expect(tileZoomFor(0.5, seg)).toBe(2);
    expect(tileZoomFor(4.2, seg)).toBe(4);
  });

  test('visible tiles intersect view and segment bounds', () => {
    const seg = segment('meps', times('2026-11-27T06:00:00Z', 1, 2), 1);
    const tiles = visibleTiles([0, 60, 20, 70], 5, seg);
    expect(tiles.length).toBeGreaterThan(0);
    for (const t of tiles) expect(t.z).toBe(5);
    expect(visibleTiles([20, 0, 30, 10], 5, seg)).toEqual([]);
  });
});
