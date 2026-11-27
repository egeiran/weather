/**
 * WeatherLayers: framework-agnostic controller. Attach to a maplibre-gl Map, then drive it with
 * setActiveLayer / setTime / setVisible / setParticles / setThresholds. All network access goes
 * through the injected `fetch` and `baseUrl`, so a host can serve the files behind its own auth.
 */
import type { Map as MapLibreMap } from 'maplibre-gl';

import { WeatherRenderer, type Scene, type Theme, type ThresholdStyle } from './gl/renderer';
import { availableLayers, loadManifest } from './manifest';
import { getRamp, type Ramp, type RampFamily } from './ramps';
import { cellSeries, chunkFor, chunkUrl, parseChunk, type Chunk } from './series';
import {
  DEFAULT_THRESHOLDS,
  THRESHOLD_VARIABLE,
  firstExceedance,
  type Exceedance,
  type ThresholdLayer,
  type Thresholds,
} from './thresholds';
import {
  layerRange,
  manifestRange,
  resolveTime,
  stepTime,
  type ResolvedTime,
  type TimeRange,
} from './time';
import { TileStore } from './tileStore';
import type { AttributionInfo, FetchFn, LayerId, Manifest, SourceInfo } from './types';

export type ParticlesSetting = boolean | 'auto';
export type ArrowsSetting = boolean | 'auto';

export interface WeatherLayersOptions {
  /** URL of the directory that holds manifest.json (relative URLs are resolved by fetch). */
  baseUrl: string;
  /** Injected fetch (e.g. adds an Authorization header). Defaults to globalThis.fetch. */
  fetch?: FetchFn;
  layer?: LayerId;
  time?: Date;
  visible?: boolean;
  /** 'auto' (default): on unless prefers-reduced-motion or a slow/save-data connection. */
  particles?: ParticlesSetting;
  /**
   * Direction arrows. 'auto' (default): shown whenever particles are off (by choice, reduced
   * motion or a slow connection) — arrows are much cheaper on the GPU.
   */
  arrows?: ArrowsSetting;
  thresholds?: Partial<Thresholds>;
  thresholdsEnabled?: boolean;
  thresholdStyle?: ThresholdStyle;
  rampFamily?: RampFamily;
  theme?: Theme;
  /** Overall opacity multiplier for the colour field (0..1). */
  opacity?: number;
  /** Insert the weather layer before this style layer (default: first symbol layer). */
  beforeId?: string;
  /** Poll interval for manifest.json in ms (default 5 min; 0 = never). */
  manifestRefreshMs?: number;
  /** +1 loads sharper tiles (more bandwidth); default 0. */
  tileZoomOffset?: number;
  /** Custom layer id (default "weather-layers"). */
  id?: string;
  /**
   * Draw the coastline above the weather field so land and sea stay readable (like Windy).
   * `true` (default) finds the basemap's vector `water` layer (OpenMapTiles schema, e.g.
   * OpenFreeMap); pass `{ source, sourceLayer }` for other basemaps, or `false` to turn off.
   */
  coastline?: boolean | { source: string; sourceLayer: string };
}

export type WeatherStatus = 'loading' | 'ready' | 'no-data' | 'error' | 'hidden';

export interface ParticlesState {
  setting: ParticlesSetting;
  enabled: boolean;
  /** Why 'auto' turned them off. */
  reason: 'reduced-motion' | 'slow-connection' | null;
}

export interface WeatherState {
  status: WeatherStatus;
  /** i18n message key + params for the status line (null when nothing to say). */
  message: { key: string; params?: Record<string, string> } | null;
  manifest: Manifest | null;
  layer: LayerId;
  layers: LayerId[];
  visible: boolean;
  requestedTime: Date;
  resolved: ResolvedTime | null;
  /** Union range across layers: what a host timeline should offer. */
  range: TimeRange | null;
  /** Range of the active layer. */
  layerRange: TimeRange | null;
  particles: ParticlesState;
  /** Whether arrows are drawn now (resolved from `arrowsSetting`). */
  arrows: boolean;
  arrowsSetting: ArrowsSetting;
  thresholds: Thresholds;
  thresholdsEnabled: boolean;
  thresholdStyle: ThresholdStyle;
  rampFamily: RampFamily;
  ramp: Ramp;
  theme: Theme;
  /** Tiles still loading for the current view/time. */
  loading: boolean;
  /** Bytes of tiles fetched so far (for budgets/diagnostics). */
  bytesLoaded: number;
  tileRequests: number;
  tileErrors: number;
}

export interface PointForecast {
  lngLat: { lng: number; lat: number };
  cell: { lng: number; lat: number };
  times: Date[];
  values: Record<string, (number | null)[]>;
  /** Index into `times` of the step in force at the requested time (or null). */
  index: number | null;
  exceedances: Exceedance[];
  sources: string[];
  bytes: number;
}

type Listener = (state: WeatherState) => void;

function prefersReducedMotion(): boolean {
  return typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
}

interface NetworkInformationLike {
  saveData?: boolean;
  effectiveType?: string;
  addEventListener?: (t: string, cb: () => void) => void;
}

function slowConnection(): boolean {
  const c = (globalThis.navigator as Navigator & { connection?: NetworkInformationLike })
    ?.connection;
  if (!c) return false;
  return Boolean(c.saveData) || ['slow-2g', '2g', '3g'].includes(c.effectiveType ?? '');
}

export class WeatherLayers {
  private opts: Required<
    Omit<WeatherLayersOptions, 'beforeId' | 'time' | 'thresholds' | 'fetch'>
  > & {
    beforeId?: string;
  };
  private fetchFn: FetchFn;
  private map: MapLibreMap | null = null;
  private renderer: WeatherRenderer | null = null;
  private store: TileStore;
  private manifest: Manifest | null = null;
  private manifestError: string | null = null;
  private time: Date;
  private thresholds: Thresholds;
  private particlesSetting: ParticlesSetting;
  private lastDrawn: ResolvedTime | null = null;
  private listeners = new Set<Listener>();
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private chunkCache = new Map<string, Promise<{ chunk: Chunk; bytes: number }>>();
  private frameComplete = true;
  private emitQueued = false;
  private abort = new AbortController();

  constructor(options: WeatherLayersOptions) {
    this.opts = {
      baseUrl: options.baseUrl,
      layer: options.layer ?? 'wind',
      visible: options.visible ?? true,
      particles: options.particles ?? 'auto',
      arrows: options.arrows ?? 'auto',
      thresholdsEnabled: options.thresholdsEnabled ?? true,
      thresholdStyle: options.thresholdStyle ?? 'hatch',
      rampFamily: options.rampFamily ?? 'calm',
      theme: options.theme ?? 'light',
      opacity: options.opacity ?? 1,
      beforeId: options.beforeId,
      manifestRefreshMs: options.manifestRefreshMs ?? 5 * 60_000,
      tileZoomOffset: options.tileZoomOffset ?? 0,
      id: options.id ?? 'weather-layers',
      coastline: options.coastline ?? true,
    };
    this.fetchFn = options.fetch ?? ((input, init) => globalThis.fetch(input, init));
    this.time = options.time ?? new Date();
    this.thresholds = { ...DEFAULT_THRESHOLDS, ...(options.thresholds ?? {}) };
    this.particlesSetting = this.opts.particles;
    this.store = new TileStore(this.fetchFn, () => {
      this.map?.triggerRepaint();
      this.queueEmit();
    });
  }

  private onMotionChange = () => this.changed();

  // -- lifecycle ---------------------------------------------------------------------------

  addTo(map: MapLibreMap): this {
    this.map = map;
    this.abort = new AbortController();
    this.renderer = new WeatherRenderer(
      this.opts.id,
      this.store,
      () => this.scene(),
      (info) => {
        if (info.complete !== this.frameComplete) {
          this.frameComplete = info.complete;
          this.queueEmit();
        }
        if (info.complete && this.currentResolved()) this.lastDrawn = this.currentResolved();
      },
    );
    const attach = () => {
      if (!this.map || !this.renderer) return;
      try {
        const before = this.opts.beforeId ?? this.firstSymbolLayer();
        if (!this.map.getLayer(this.opts.id)) this.map.addLayer(this.renderer, before);
        this.addCoastline(before);
      } catch {
        // Style not ready yet ("Style is not done loading"): the next styledata event retries.
      }
    };
    attach();
    // 'style.load' after setStyle (light/dark switch, context restore); 'styledata' covers maps
    // whose style finished loading while tiles were still streaming (isStyleLoaded() false).
    map.on('style.load', attach);
    map.on('styledata', attach);
    this.detachers.push(() => {
      map.off('style.load', attach);
      map.off('styledata', attach);
    });
    if (typeof matchMedia === 'function') {
      const mq = matchMedia('(prefers-reduced-motion: reduce)');
      mq.addEventListener?.('change', this.onMotionChange);
      this.detachers.push(() => mq.removeEventListener?.('change', this.onMotionChange));
    }
    void this.refresh();
    if (this.opts.manifestRefreshMs > 0) {
      this.pollTimer = setInterval(() => void this.refresh(), this.opts.manifestRefreshMs);
    }
    return this;
  }

  private detachers: (() => void)[] = [];

  /** Detach from the map. The controller can be added to a map again later. */
  remove() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
    this.detachers.forEach((d) => d());
    this.detachers = [];
    this.abort.abort();
    if (this.map?.getLayer(this.coastlineId)) this.map.removeLayer(this.coastlineId);
    if (this.map?.getLayer(this.opts.id)) this.map.removeLayer(this.opts.id);
    this.map = null;
    this.renderer = null;
  }

  private get coastlineId(): string {
    return `${this.opts.id}-coastline`;
  }

  /** Where the coastline comes from: an explicit source or the basemap's `water` fill layer. */
  private coastlineSource(): { source: string; sourceLayer: string } | null {
    const c = this.opts.coastline;
    if (c === false) return null;
    if (typeof c === 'object') return c;
    const layers = this.map?.getStyle()?.layers ?? [];
    for (const l of layers) {
      const sl = (l as { 'source-layer'?: string })['source-layer'];
      const src = (l as { source?: string }).source;
      if (l.type === 'fill' && sl === 'water' && typeof src === 'string') {
        return { source: src, sourceLayer: sl };
      }
    }
    return null;
  }

  /** Coastline above the weather field and below labels; colour follows the theme. */
  private addCoastline(before: string | undefined) {
    const map = this.map;
    if (!map || map.getLayer(this.coastlineId)) return;
    const src = this.coastlineSource();
    if (!src || !map.getSource(src.source)) return;
    map.addLayer(
      {
        id: this.coastlineId,
        type: 'line',
        source: src.source,
        'source-layer': src.sourceLayer,
        // Sea only (fjords included); lake outlines would clutter mid zooms.
        filter: ['==', ['get', 'class'], 'ocean'],
        layout: { 'line-join': 'round', visibility: this.coastlineVisible() ? 'visible' : 'none' },
        paint: {
          'line-color': this.coastlineColor(),
          'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.6, 7, 1.0, 11, 1.6],
        },
      },
      before,
    );
  }

  private coastlineColor(): string {
    return this.opts.theme === 'dark' ? 'rgba(236, 242, 248, 0.62)' : 'rgba(22, 34, 46, 0.6)';
  }

  private coastlineVisible(): boolean {
    return this.opts.visible && !!this.manifest;
  }

  private syncCoastline() {
    const map = this.map;
    if (!map?.getLayer(this.coastlineId)) return;
    map.setPaintProperty(this.coastlineId, 'line-color', this.coastlineColor());
    map.setLayoutProperty(
      this.coastlineId,
      'visibility',
      this.coastlineVisible() ? 'visible' : 'none',
    );
  }

  /** Remove from the map and drop all listeners (final). */
  destroy() {
    this.remove();
    this.listeners.clear();
  }

  private firstSymbolLayer(): string | undefined {
    const layers = this.map?.getStyle()?.layers ?? [];
    return layers.find((l) => l.type === 'symbol')?.id;
  }

  /** (Re)load manifest.json. Called on add and on a timer. */
  async refresh(): Promise<void> {
    try {
      const m = await loadManifest(this.fetchFn, this.opts.baseUrl, this.abort.signal);
      if (!this.manifest || m.generated_at !== this.manifest.generated_at) {
        this.manifest = m;
        this.chunkCache.clear();
        this.store.resetErrors();
      }
      this.manifestError = null;
    } catch (err) {
      if ((err as Error).name === 'AbortError') return;
      this.manifestError = (err as Error).message;
    }
    this.changed();
  }

  // -- public API --------------------------------------------------------------------------

  setVisible(visible: boolean) {
    this.opts.visible = visible;
    this.changed();
  }
  setActiveLayer(layer: LayerId) {
    this.opts.layer = layer;
    this.changed();
  }
  setTime(time: Date) {
    this.time = new Date(time.getTime());
    this.changed();
  }
  setParticles(setting: ParticlesSetting) {
    this.particlesSetting = setting;
    this.changed();
  }
  setArrows(on: ArrowsSetting) {
    this.opts.arrows = on;
    this.changed();
  }
  setThresholds(t: Partial<Thresholds>) {
    this.thresholds = { ...this.thresholds, ...t };
    this.changed();
  }
  setThresholdsEnabled(on: boolean) {
    this.opts.thresholdsEnabled = on;
    this.changed();
  }
  setThresholdStyle(style: ThresholdStyle) {
    this.opts.thresholdStyle = style;
    this.changed();
  }
  setRampFamily(family: RampFamily) {
    this.opts.rampFamily = family;
    this.changed();
  }
  setTheme(theme: Theme) {
    this.opts.theme = theme;
    this.changed();
  }
  setOpacity(opacity: number) {
    this.opts.opacity = Math.max(0, Math.min(1, opacity));
    this.changed();
  }

  /** Range the host's timeline should offer (union of all layers), or null before load. */
  getTimeRange(): TimeRange | null {
    return this.manifest ? manifestRange(this.manifest) : null;
  }

  /** Next/previous valid time of the active layer. */
  stepTime(dir: 1 | -1): Date | null {
    const layer = this.manifest?.layers[this.opts.layer];
    return layer ? stepTime(layer, this.time, dir) : null;
  }

  getAttribution(): AttributionInfo[] {
    return this.manifest?.attribution ?? [];
  }

  getSources(): Record<string, SourceInfo> {
    return this.manifest?.sources ?? {};
  }

  on(event: 'change', cb: Listener): () => void {
    if (event !== 'change') throw new Error(`unknown event ${event}`);
    this.listeners.add(cb);
    cb(this.getState());
    return () => this.listeners.delete(cb);
  }

  getState(): WeatherState {
    const m = this.manifest;
    const layerInfo = m?.layers[this.opts.layer] ?? null;
    const resolved = this.currentResolved();
    const particles = this.particlesState();
    let status: WeatherStatus;
    let message: WeatherState['message'] = null;
    if (!this.opts.visible) status = 'hidden';
    else if (!m && this.manifestError) {
      status = 'error';
      message = { key: 'status.manifestError' };
    } else if (!m) status = 'loading';
    else if (!layerInfo || !resolved) {
      status = 'no-data';
      message = layerInfo
        ? { key: 'status.noDataAtTime', params: { start: layerInfo.start, end: layerInfo.end } }
        : { key: 'status.noDataAtTime', params: { start: '', end: '' } };
    } else status = 'ready';
    if (status === 'ready' && this.store.stats.errors > 0) message = { key: 'status.tileError' };
    return {
      status,
      message,
      manifest: m,
      layer: this.opts.layer,
      layers: m ? availableLayers(m) : [],
      visible: this.opts.visible,
      requestedTime: this.time,
      resolved,
      range: m ? manifestRange(m) : null,
      layerRange: layerInfo ? layerRange(layerInfo) : null,
      particles,
      arrows: this.arrowsEnabled(particles.enabled),
      arrowsSetting: this.opts.arrows,
      thresholds: this.thresholds,
      thresholdsEnabled: this.opts.thresholdsEnabled,
      thresholdStyle: this.opts.thresholdStyle,
      rampFamily: this.opts.rampFamily,
      ramp: getRamp(this.opts.layer, this.opts.rampFamily),
      theme: this.opts.theme,
      loading: status === 'ready' && (this.store.loading || !this.frameComplete),
      bytesLoaded: this.store.stats.bytes,
      tileRequests: this.store.stats.requests,
      tileErrors: this.store.stats.errors,
    };
  }

  /**
   * Values at a point: one request (the series chunk), cached per manifest.
   * Returns null when the point is outside the data.
   */
  async queryPoint(lngLat: { lng: number; lat: number }): Promise<PointForecast | null> {
    const m = this.manifest;
    if (!m?.series) return null;
    const ref = chunkFor(m.series, lngLat.lng, lngLat.lat);
    if (!ref) return null;
    const url = chunkUrl(this.opts.baseUrl, m.series, ref);
    let p = this.chunkCache.get(url);
    if (!p) {
      p = (async () => {
        const res = await this.fetchFn(url, { signal: this.abort.signal });
        if (!res.ok) throw new Error(`series: HTTP ${res.status}`);
        const buf = new Uint8Array(await res.arrayBuffer());
        return { chunk: await parseChunk(buf), bytes: buf.byteLength };
      })();
      this.chunkCache.set(url, p);
      p.catch(() => this.chunkCache.delete(url));
    }
    const { chunk, bytes } = await p;
    const values = cellSeries(m.series, chunk, ref.row, ref.col);
    const times = m.series.times.map((t) => new Date(t));
    const now = this.time.getTime();
    let index: number | null = null;
    times.forEach((t, i) => {
      if (t.getTime() <= now) index = i;
    });
    const exceedances: Exceedance[] = (Object.keys(THRESHOLD_VARIABLE) as ThresholdLayer[]).flatMap(
      (layer) => {
        const thr = this.thresholds[layer];
        const vals = values[THRESHOLD_VARIABLE[layer]];
        if (thr === null || !vals) return [];
        return [{ layer, threshold: thr, ...firstExceedance(times, vals, thr, this.time) }];
      },
    );
    const sources = [
      ...new Set(m.series.variables.flatMap((v) => v.segments.map((s) => s.source))),
    ];
    return {
      lngLat,
      cell: { lng: ref.cellLon, lat: ref.cellLat },
      times,
      values,
      index,
      exceedances,
      sources,
      bytes,
    };
  }

  // -- internals ---------------------------------------------------------------------------

  private particlesState(): ParticlesState {
    const setting = this.particlesSetting;
    const layer = this.manifest?.layers[this.opts.layer];
    if (setting === 'auto') {
      if (prefersReducedMotion()) return { setting, enabled: false, reason: 'reduced-motion' };
      if (slowConnection()) return { setting, enabled: false, reason: 'slow-connection' };
      return { setting, enabled: layer?.particles ?? true, reason: null };
    }
    return { setting, enabled: setting && (layer?.particles ?? true), reason: null };
  }

  private arrowsEnabled(particlesOn: boolean): boolean {
    return this.opts.arrows === 'auto' ? !particlesOn : this.opts.arrows;
  }

  private currentResolved(): ResolvedTime | null {
    const layer = this.manifest?.layers[this.opts.layer];
    return layer ? resolveTime(layer, this.time) : null;
  }

  private scene(): Scene {
    const layer = this.manifest?.layers[this.opts.layer] ?? null;
    const resolved = this.currentResolved();
    let prefetch: ResolvedTime | null = null;
    if (layer && resolved) {
      const next = stepTime(layer, resolved.time, 1);
      prefetch = next ? resolveTime(layer, next) : null;
    }
    const thresholdLayer =
      this.opts.layer in THRESHOLD_VARIABLE ? (this.opts.layer as ThresholdLayer) : null;
    const threshold =
      this.opts.thresholdsEnabled && thresholdLayer ? this.thresholds[thresholdLayer] : null;
    return {
      visible: this.opts.visible && !!layer,
      layerId: this.opts.layer,
      layer,
      resolved,
      fallback: this.lastDrawn,
      prefetch,
      baseUrl: this.opts.baseUrl,
      ramp: getRamp(this.opts.layer, this.opts.rampFamily),
      opacity: this.opts.opacity,
      threshold,
      thresholdStyle: this.opts.thresholdStyle,
      theme: this.opts.theme,
      arrows: this.arrowsEnabled(this.particlesState().enabled),
      particles: this.particlesState().enabled,
      tileZoomOffset: this.opts.tileZoomOffset,
    };
  }

  private changed() {
    this.syncCoastline();
    this.map?.triggerRepaint();
    this.queueEmit();
  }

  private queueEmit() {
    if (this.emitQueued) return;
    this.emitQueued = true;
    queueMicrotask(() => {
      this.emitQueued = false;
      const s = this.getState();
      this.listeners.forEach((l) => l(s));
    });
  }
}
