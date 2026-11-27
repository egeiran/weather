# Progress

| # | Milestone | Status |
|---|-----------|--------|
| 0 | Bootstrap (layout, tooling, CLAUDE.md, README) | done |
| 1 | Data spike, data-sources.md, packaging decisions | done |
| 2 | Pipeline core: MEPS wind + gusts | done |
| 3 | Layer core + demo + Playwright | done |
| 4 | Waves + currents | done (WW3 4 km, NorKyst v3) |
| 5 | ECMWF days 3–10, stitching | done |
| 6 | Particles | done |
| 7 | Click for values + thresholds | done |
| 8 | Hardening, cross-check, full-coast run | done |
| 9 | Docs + independent review | done |

## Results

- Cross-check (docs/crosscheck.md), tiles at MET's grid point: wind 0.05 m/s / 0.7°, gust 0.06 m/s,
  current 0.04 kn / 3.0°, sea temperature 0.04 °C (mean abs diff); waves 0.14 m / 11° (WW3 4 km vs
  MET's WAM 800 m near the coast). Click series agree within 0.2–0.25 (lattice resolution).
- Performance (docs/performance.md): first view ≤ 398 KB, step change ≤ 177 KB, click = 1 request
  (7–11 KB), 60 fps with particles (Apple M4, 1440×900 @2x).
- Full coast: 4 min 42 s, 1.87 GB downloaded, 268 MB public + 371 MB state, 17,631 files;
  no-op rerun 4.3 s / 4 requests / 12 KB.
- Clean clone: `make setup && make pipeline && make dev` verified.

## Independent review (cold read by a subagent) — all findings fixed

1. Renderer kept deleted GL objects after a style reload/context restore → references cleared in `onRemove`.
2. One-hour hole at the regional → ECMWF boundary → `resolveTime` picks the nearer boundary time.
3. First exceedance skipped the variable's own step on the union axis → per-variable step in force.
4. Threshold marking used ≥ and filled flat plateaus → strict >, no contour where `fwidth` ≈ 0.
5. `addTo` could miss attaching while tiles stream → attach retried on `styledata`/`style.load`.
6. Failed tiles never retried → exponential backoff (2–60 s), error count = tiles currently failing.
7. Raw cache grew unbounded in production → cache `auto` (dev only) + age pruning (48 h).
8. Fallback tiles duplicated/over-drawn while loading → computed in tile space, de-duplicated, drawn first.
9. NorKyst showed "unavailable" every morning → status `pending` while the previous run is still newest.
10. `make test` ran the live MET test → runs from `pipeline/` with its pytest config.
11. Unknown layer ids crashed the client → ignored; schema allows new ids (minor versions).
12. Tile buffer and direction offset hard-coded → schema `buffer: 1`, shader applies `offset`.
13. `--force` replaced runs non-atomically and reused stale series → swap with two renames, `build_id` in series id.
14. `public` caching advised for authenticated files → `private` in contract and demo.
15. Empty output-dir env served the whole checkout in the demo → `||` defaults + path allowlist.
16. Controller could not be re-added after `remove()`; media listener leaked → fixed, `destroy()` added.
17. Doc nits (WW3 zooms, coastline rule wording, `pending` status) → corrected.

Regression tests were added for 2, 3, 4, 6, 9, 11 and 13.

## Second round (owner feedback, 2026-11-27)

- Look chosen: calm ramp, hatching, subtle Windy-like particles, arrows automatic/optional.
- Particles no longer pile up after zoom (hidden while moving, reseeded when still).
- Polygon areas + strip-wise fetching; `norway` polygon halves the download (decision 0010).
- Coastline drawn above the weather field (light/dark aware).
- Windy-style UI: layer rail, slim legend, settings popover, model/run in the timeline, draggable pin.
- Fjord waves: MyWaveWAM 800 m overlays on WW3 (00/12Z for large areas); ECMWF waves follow
  WW3's coastline (decision 0011). Windy ECMWF comparison in docs/validation.md.

## Third round (2026-11-27)

- Public demo on GitHub Pages (https://egeiran.github.io/weather/), updated four times a day.
- Issues #1–#4: water level/tide, smooth time interpolation, uncertainty, more layers.
- Finer days 3–10 (decision 0012): ECMWF 0.1° for wind/gusts, MyWaveWAM 3 km (`wam3`) for waves
  and swell after WW3 — swell now reaches ~day 9; ECMWF waves only as fallback. ≈ 3.5 GB/day.
- A source configuration change (model/products) rebuilds and republishes the same run id.

## Next steps

- Norway locally: `make pipeline-norway` then `make dev-norway` (port 5175, own data dirs).

- Look chosen by the owner: calm ramp, hatching, subtle Windy-like particles by default, arrows
  as automatic fallback ('auto') or on demand (decisions 0008, 0009).
- Wire into Fleet Tracker (docs/host-integration.md): serve `data/out` behind the API's auth,
  add `weather-layers` as a workspace package, mount `<WeatherOverlay>`, drive `time` from the host timeline.
- Run the pipeline hourly on a host with ~2 GB RAM / 5 GB disk; set `WEATHER_LAYERS_USER_AGENT`.
- Optional: row-band fetching for rotated grids (≈ −⅓ download), blob-storage `Storage`, globe support.

## Known gaps

- Waves/swell end at +234 h from the 18Z MyWaveWAM run (≈ 12 h before wind); currents end at +120 h.
- Fjord waves (800 m grids) only for the first ~66 h; afterwards MyWaveWAM 3 km resolves wider fjords only.
- Point series use a ~2.8 km lattice: values can differ from the colour field in strong gradients.
- Globe projection not supported by the custom layer (mercator only).
