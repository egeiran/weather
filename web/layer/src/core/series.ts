/**
 * Point series ("WLS1" chunks): one request per click returns every variable over the whole
 * stitched timeline for a 4x4 block of lattice cells. Format: see docs/contract.md.
 */
import { joinUrl } from './manifest';
import { maskFor } from './tiles';
import type { FetchFn, SeriesInfo, SeriesVariable } from './types';

export interface ChunkRef {
  cy: number;
  cx: number;
  row: number; // cell row inside the chunk (south -> north)
  col: number; // cell column inside the chunk (west -> east)
  cellLat: number; // cell centre
  cellLon: number;
}

export function chunkFor(series: SeriesInfo, lon: number, lat: number): ChunkRef | null {
  const g = series.grid;
  const r = Math.floor((lat - g.origin[1]) / g.dlat);
  const c = Math.floor((lon - g.origin[0]) / g.dlon);
  if (r < g.row0 || r >= g.row0 + g.rows || c < g.col0 || c >= g.col0 + g.cols) return null;
  const cy = Math.floor(r / g.chunk);
  const cx = Math.floor(c / g.chunk);
  if (!maskFor(series.availability).has(cx, cy)) return null;
  return {
    cy,
    cx,
    row: r - cy * g.chunk,
    col: c - cx * g.chunk,
    cellLat: g.origin[1] + (r + 0.5) * g.dlat,
    cellLon: g.origin[0] + (c + 0.5) * g.dlon,
  };
}

export function chunkUrl(baseUrl: string, series: SeriesInfo, ref: ChunkRef): string {
  return joinUrl(
    baseUrl,
    series.template.replace('{cy}', String(ref.cy)).replace('{cx}', String(ref.cx)),
  );
}

export interface Chunk {
  rows: number;
  cols: number;
  nvars: number;
  ntimes: number;
  data: Uint8Array;
}

async function gunzip(bytes: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([bytes as BlobPart])
    .stream()
    .pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Parse a chunk; accepts gzip (as stored) or already-decompressed bytes (proxy did it). */
export async function parseChunk(raw: Uint8Array): Promise<Chunk> {
  const bytes = raw[0] === 0x1f && raw[1] === 0x8b ? await gunzip(raw) : raw;
  const magic = String.fromCharCode(bytes[0]!, bytes[1]!, bytes[2]!, bytes[3]!);
  if (magic !== 'WLS1') throw new Error('not a WLS1 series chunk');
  const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const rows = dv.getUint16(4, true);
  const cols = dv.getUint16(6, true);
  const nvars = dv.getUint16(8, true);
  const ntimes = dv.getUint16(10, true);
  const data = bytes.subarray(12, 12 + rows * cols * nvars * ntimes);
  if (data.length !== rows * cols * nvars * ntimes) throw new Error('truncated series chunk');
  return { rows, cols, nvars, ntimes, data };
}

export async function fetchChunk(
  fetchFn: FetchFn,
  url: string,
  signal?: AbortSignal,
): Promise<Chunk> {
  const res = await fetchFn(url, { signal });
  if (!res.ok) throw new Error(`series: HTTP ${res.status}`);
  return parseChunk(new Uint8Array(await res.arrayBuffer()));
}

export function decodeCode(v: Pick<SeriesVariable, 'scale' | 'offset' | 'nodata'>, code: number) {
  return code === v.nodata ? null : v.offset + v.scale * code;
}

/** Values of every variable at one cell: name -> (number | null)[] aligned with series.times. */
export function cellSeries(
  series: SeriesInfo,
  chunk: Chunk,
  row: number,
  col: number,
): Record<string, (number | null)[]> {
  const out: Record<string, (number | null)[]> = {};
  const { rows, cols, ntimes } = chunk;
  series.variables.forEach((v, vi) => {
    const base = ((vi * rows + row) * cols + col) * ntimes;
    const arr: (number | null)[] = new Array(ntimes);
    for (let t = 0; t < ntimes; t++) arr[t] = decodeCode(v, chunk.data[base + t]!);
    out[v.name] = arr;
  });
  return out;
}
