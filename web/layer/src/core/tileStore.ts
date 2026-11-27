/**
 * Fetches value tiles through the injected fetch, decodes them off the main GL path and hands
 * the decoded bitmaps to the renderer, which uploads them inside MapLibre's render hooks.
 */
import type { FetchFn } from './types';

export type TileState = 'loading' | 'decoded' | 'ready' | 'error' | 'missing';

export interface TileEntry {
  url: string;
  state: TileState;
  bitmap?: ImageBitmap;
  texture?: WebGLTexture;
  bytes: number;
  lastUsed: number;
  priority: number;
  abort?: AbortController;
}

export interface TileStoreStats {
  requests: number;
  bytes: number;
  errors: number;
  inFlight: number;
}

export async function decodeTileBlob(blob: Blob): Promise<ImageBitmap> {
  // Values must survive decoding bit-exactly: no premultiplication, no colour management.
  return createImageBitmap(blob, { premultiplyAlpha: 'none', colorSpaceConversion: 'none' });
}

export class TileStore {
  private entries = new Map<string, TileEntry>();
  private queue: TileEntry[] = [];
  private inFlight = 0;
  private clock = 0;
  readonly stats: TileStoreStats = { requests: 0, bytes: 0, errors: 0, inFlight: 0 };

  constructor(
    private fetchFn: FetchFn,
    private onChange: () => void,
    private maxEntries = 320,
    private maxConcurrent = 6,
  ) {}

  tick(): number {
    return ++this.clock;
  }

  get(url: string): TileEntry | undefined {
    const e = this.entries.get(url);
    if (e) e.lastUsed = this.clock;
    return e;
  }

  /** Request a tile. Lower priority number = sooner. Re-requests just update priority. */
  request(url: string, priority = 0): TileEntry {
    let e = this.entries.get(url);
    if (e) {
      e.lastUsed = this.clock;
      if (e.state === 'loading' && !e.abort) e.priority = Math.min(e.priority, priority);
      return e;
    }
    e = { url, state: 'loading', bytes: 0, lastUsed: this.clock, priority };
    this.entries.set(url, e);
    this.queue.push(e);
    this.pump();
    return e;
  }

  /** Drop queued (not yet started) requests that are no longer wanted. */
  cancelQueuedExcept(wanted: Set<string>) {
    this.queue = this.queue.filter((e) => {
      if (wanted.has(e.url)) return true;
      this.entries.delete(e.url);
      return false;
    });
  }

  private pump() {
    this.queue.sort((a, b) => a.priority - b.priority);
    while (this.inFlight < this.maxConcurrent && this.queue.length) {
      const e = this.queue.shift()!;
      this.load(e);
    }
    this.stats.inFlight = this.inFlight;
  }

  private async load(e: TileEntry) {
    this.inFlight++;
    this.stats.inFlight = this.inFlight;
    e.abort = new AbortController();
    try {
      const res = await this.fetchFn(e.url, { signal: e.abort.signal });
      this.stats.requests++;
      if (res.status === 404) {
        e.state = 'missing';
      } else if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      } else {
        const blob = await res.blob();
        e.bytes = blob.size;
        this.stats.bytes += blob.size;
        e.bitmap = await decodeTileBlob(blob);
        e.state = 'decoded';
      }
    } catch (err) {
      if ((err as Error).name !== 'AbortError') {
        e.state = 'error';
        this.stats.errors++;
      } else {
        this.entries.delete(e.url);
      }
    } finally {
      this.inFlight--;
      this.stats.inFlight = this.inFlight;
      e.abort = undefined;
      this.pump();
      this.onChange();
    }
  }

  /** Called by the renderer inside a GL hook: upload decoded bitmaps (bounded per frame). */
  uploadPending(upload: (bitmap: ImageBitmap) => WebGLTexture, maxPerFrame = 12): number {
    let n = 0;
    for (const e of this.entries.values()) {
      if (e.state !== 'decoded' || !e.bitmap) continue;
      e.texture = upload(e.bitmap);
      e.bitmap.close();
      e.bitmap = undefined;
      e.state = 'ready';
      if (++n >= maxPerFrame) break;
    }
    return n;
  }

  hasPendingUploads(): boolean {
    for (const e of this.entries.values()) if (e.state === 'decoded') return true;
    return false;
  }

  /** Evict least-recently-used ready tiles beyond the cap (inside a GL hook). */
  prune(deleteTexture: (t: WebGLTexture) => void) {
    if (this.entries.size <= this.maxEntries) return;
    const victims = [...this.entries.values()]
      .filter((e) => e.state !== 'loading' && e.lastUsed < this.clock - 2)
      .sort((a, b) => a.lastUsed - b.lastUsed)
      .slice(0, this.entries.size - this.maxEntries);
    for (const v of victims) {
      if (v.texture) deleteTexture(v.texture);
      v.bitmap?.close();
      this.entries.delete(v.url);
    }
  }

  get loading(): boolean {
    return this.inFlight > 0 || this.queue.length > 0;
  }

  destroy(deleteTexture?: (t: WebGLTexture) => void) {
    for (const e of this.entries.values()) {
      e.abort?.abort();
      if (e.texture && deleteTexture) deleteTexture(e.texture);
      e.bitmap?.close();
    }
    this.entries.clear();
    this.queue = [];
  }
}
