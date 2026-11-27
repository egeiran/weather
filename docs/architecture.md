# Architecture

```
            ┌──────────────── pipeline (Python, hourly job) ────────────────┐
 THREDDS    │ discover ─► fetch subset ─► rotate ─► regrid ─► encode ─► write │   static files
 (OPeNDAP)  │  latest     (OPeNDAP /     to E/N   to Web     8-bit    tiles  │   data/out/
 ECMWF  ───►│  complete   byte ranges)            Mercator   RGB      + run  ├──► manifest.json
 open data  │  run                                           PNG      .json  │    runs/…/*.png
            │                       per-run state (npy) ─► merged series ───┤    series/…/*.bin
            └──────────────────────────────────────────────────────────────┘
                                                                     │ served by the host
                                                                     ▼ behind its own auth
            ┌──────────── layer module (TypeScript, in the browser) ────────┐
            │ manifest ─► time stitching ─► visible tiles ─► injected fetch │
            │ ─► ImageBitmap (no premultiply) ─► WebGL2 textures (in render  │
            │ hooks) ─► MapLibre custom layer: colour field + threshold      │
            │ marking, vector target ─► arrows + particles                   │
            │ click ─► one series chunk ─► values, chart, first exceedance  │
            └────────────────────────────────────────────────────────────────┘
```

## Pipeline (`pipeline/src/weather_layers`)

| module | role |
|---|---|
| `cli.py` | `weather-layers run / status / validate / crosscheck` |
| `config.py` | settings from `WEATHER_LAYERS_*` environment variables |
| `http.py` | the only HTTP client: User-Agent, concurrency cap, backoff on 429/5xx honouring `Retry-After`, raw cache, byte counters |
| `dap.py` | minimal DAP2 client (DDS/DAS parsing, `.dods` decoding) so OPeNDAP goes through `http.py` |
| `sources/meps.py` · `wam.py` · `norkyst.py` · `ecmwf.py` | latest-complete-run discovery and area subsetting per source; return a regular grid + a step iterator of fields in physical units, vectors already true east/north |
| `vectors.py` | grid-angle by finite differences through pyproj, grid → earth rotation, from/to conventions, knots |
| `grids.py` | `RegularGrid` (any CRS), `Sampler` (precomputed bilinear weights, no-data aware), block-mean coarsening |
| `mercator.py` | XYZ tile math, 258-px buffered tile pixel centres |
| `products.py` | which fields make which tile channels (vectors interpolated as components) |
| `encoding.py` | 8-bit linear channel specs, PNG writing |
| `build.py` | one source run → tiles + run.json + per-run series state, written in a staging dir and promoted |
| `stitch.py` | time stitching across sources (shared by tiles and series) |
| `series.py` · `seriesgrid.py` | merged WLS1 point-series chunks on a global lattice |
| `manifest.py` · `schema.py` | manifest assembly and JSON Schema validation |
| `publish.py` | orchestration, idempotency, atomic publish, retention |
| `storage.py` | storage interface; local filesystem implementation |
| `crosscheck.py` | comparison with api.met.no point forecasts |

### A pipeline run

1. For each source: `latest_complete_run` reads the catalog (or the aggregate's time axis, or
   the ECMWF completeness marker) and checks that all needed steps exist. If
   `runs/<source>/<run_id>/run.json` already exists for this area, the source is done.
2. Otherwise `fetch` computes the index window of the area in the source grid (projecting the
   area outline into the grid CRS). For polygon areas it fetches the window in a few row strips
   that only span the polygon's columns (decision 0010). Requests are index-sliced, ≤ 24 MB;
   CF packing/fill values are unpacked and vectors rotated.
3. `build_run` plans the tiles per zoom (plus detail zooms where overlays exist) (min…max zoom per source, block-averaged inputs where a
   pixel spans several native cells), precomputes sampling weights once, then for every step
   samples, encodes and writes PNGs in a thread pool. Tile availability is fixed by the first step
   (land masks are static). The same step is sampled on the series lattice into a memory-mapped
   `.npy` in the state dir.
4. Staging directories are promoted with an atomic rename; `run.json` marks a complete run.
5. If the set of newest runs (or a source's health) changed, the merged series is built (in
   staging, then promoted), then `manifest.json` is written atomically (temp file + fsync +
   rename) — **the manifest is always written last**. Otherwise the run is a no-op.
6. Retention keeps the newest N runs per source (and anything the current or previous manifest
   references) and the current + previous series, and removes crashed staging directories.

A failing source never blocks the others: it is logged, marked `stale` (previous run still
published) or `missing` in the manifest, and the client shows a warning.

## Layer module (`web/layer/src`)

| path | role |
|---|---|
| `core/WeatherLayers.ts` | public controller: `addTo(map)`, `setActiveLayer`, `setTime`, `setVisible`, `setParticles`, `setArrows`, `setThresholds`, `setThresholdStyle`, `setRampFamily`, `setTheme`, `setOpacity`, `getTimeRange`, `stepTime`, `queryPoint`, `on('change')` |
| `core/gl/renderer.ts` | the MapLibre `CustomLayerInterface` (one layer, inserted below the first symbol layer) |
| `core/gl/shaders.ts` | GLSL ES 3.00: colour field with manual bilinear + threshold marking; vector pass; arrows |
| `core/gl/particles.ts` | webgl-wind style particles: RGBA8 state textures, GPU advection, fading trails |
| `core/tileStore.ts` | fetch via injected fetch, decode to `ImageBitmap`, upload inside render hooks, LRU |
| `core/time.ts` · `tiles.ts` · `series.ts` · `thresholds.ts` · `ramps.ts` · `units.ts` · `i18n.ts` | pure logic (unit tested) |
| `core/decode.ts` | CPU reference of the shader decoding |
| `react/*` | `WeatherOverlay` for react-map-gl 8, `useWeatherLayers`, UI components, `styles.css` |
| `i18n/nb.json`, `en.json` | all user-facing text |

### Rendering per frame

- `prerender`: upload decoded tiles; compute the draw list for the current view and time
  (tile zoom = `clamp(floor(mapZoom), minzoom, maxzoom)`, fallbacks: a loaded ancestor tile, then
  the previously shown time); render the **vector target** (half resolution RGBA8: normalised
  east/north motion + validity) when arrows or particles are on; advance particles and draw them
  into the trail texture.
- `render`: draw the colour field per tile (ramp lookup in a 256×1 texture, threshold
  hatching/tint/contour with a colour chosen from the field's luminance), composite particle
  trails, draw arrows (instanced glyphs at a mercator-aligned grid whose spacing stays 46–92 CSS px
  at any zoom; each samples the vector target and is rotated with the map's local north/east).
- MapLibre marks its GL state dirty after both hooks, so the layer can bind its own state freely.

### Time

`resolveTime(layer, t)` picks the segment whose nearest valid time is within half a step of `t`;
otherwise the layer reports "no data at this time" and draws nothing. The next step's tiles are
prefetched once the current step is complete, for smooth playback.

## Why things are the way they are

See `docs/decisions/`: tile packaging (0001), encoding (0002), series format (0003), wave source
(0004), regridding (0005), stitching and ECMWF (0006), coast data volume (0007), ramps (0008),
particles (0009).
