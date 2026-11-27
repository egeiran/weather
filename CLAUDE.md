# CLAUDE.md — weather-layers

Gridded weather layers (wind, gusts, waves, currents) for a vessel-tracking MapLibre map.
Two parts joined by **files on disk** (the contract): a Python pipeline that writes
value-encoded tiles + point series + `manifest.json`, and a TypeScript layer module that draws them.

Read `docs/PROGRESS.md` first when resuming work (milestones, what's next, open issues).

## Layout

```
pipeline/     Python package `weather_layers` + CLI `weather-layers` (uv, ruff, pytest)
web/layer/    TypeScript module `weather-layers` (core: framework-agnostic; react/: adapter + UI)
web/demo/     Vite + React demo (react-map-gl/maplibre + OpenFreeMap); serves data/out at /weather-data
schema/       manifest JSON Schema (contract, versioned)
docs/         architecture, data sources, contract, host integration, deployment, decisions/
data/         (gitignored) out/ = published files, state/ = pipeline state, cache/ = raw downloads
```

## Commands (run from repo root)

- Setup: `make setup` (uv sync + npm install + playwright chromium)
- Pipeline, dev area: `make pipeline` (= `uv run --project pipeline weather-layers run --area dev`)
- Pipeline, coast: `make pipeline-coast`
- Dev (demo + data): `make dev` → http://localhost:5173
- Tests: `make test` (pytest + vitest); lint: `make lint` (ruff + eslint + prettier); `make typecheck`
- Screenshots: `make screenshots` (Playwright; writes docs/screenshots/)
- Live checks against MET: `uv run --project pipeline pytest -m live`; cross-check: `make crosscheck`

## Hard rules

- No Docker, no paid services/API keys/accounts, no database or cloud resources.
- Never commit data (tiles, model files, big fixtures). Fixtures must be tiny/synthetic.
- Commits: clear messages, **no Co-Authored-By or AI attribution** anywhere. Push to `origin main` after each milestone.
- Only permissive-licence dependencies (MIT/BSD/ISC/Apache-2.0).
- Code/comments/docs in English. UI text only via `web/layer/src/i18n/{nb,en}.json` (identical keys, nb default).
- Record significant choices in `docs/decisions/NNNN-title.md`. Keep `docs/PROGRESS.md` current.

## MET Norway etiquette (enforced in `pipeline/src/weather_layers/http.py`)

- Identifying `User-Agent` (`WEATHER_LAYERS_USER_AGENT`, default `weather-layers/<ver> (+https://github.com/egeiran/weather)`).
- Subset by index via OPeNDAP (own DAP2 client in `dap.py`); never whole files. Fetch each model run once.
- Cache raw downloads in dev (`data/cache`), concurrency cap (`WEATHER_LAYERS_CONCURRENCY`), backoff on 429/5xx.
- Browser never calls MET/ECMWF. api.met.no point APIs only for the cross-check (4-decimal coords).

## Traps (each has a test — keep it that way)

- **Grid-relative vectors**: MEPS `x_wind_10m/y_wind_10m` are along the Lambert grid axes → rotate
  with `vectors.grid_north_angle` + `rotate_grid_to_earth`. NorKyst: use `u_eastward/v_northward`, not `u/v`.
- **Direction conventions**: wind & waves = "from" (meteorological); currents = "to" (oceanographic).
  Internally (u, v) are always the true east/north *motion*. Arrows/particles show motion.
- **Grids**: MEPS Lambert, NorKyst polar stereographic, WAM rotated pole, ECMWF lat/lon. All regridded
  by pyproj forward transform → fractional index → bilinear (`grids.py`). Never assume lat/lon arrays are regular.
- **No data**: code 255 in every channel; ocean models are no-data over land. Drawn transparent.
- **Premultiplied alpha**: tiles are RGB PNGs (no alpha). Client decodes with `premultiplyAlpha: 'none'`,
  `colorSpaceConversion: 'none'` and NEAREST sampling + manual bilinear in the shader.
- **Run lag/partial runs**: a run counts only when all needed steps exist (`sources/*.py: latest_complete_run`).

## Conventions

- Tiles: 256 px + 1 px buffer (258×258) RGB PNG, XYZ dirs per valid time. See `docs/contract.md`.
- Units on the wire = display units: m/s (wind, gust), m (waves), s (period), kn (current), °C.
- Python: type hints, ruff (line 100). TS: strict, ESLint + Prettier, Vitest.
