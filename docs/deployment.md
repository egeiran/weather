# Deployment

The pipeline is a batch job that writes static files. It needs Python (via `uv`), outbound
HTTPS to `thredds.met.no` and the ECMWF open-data mirror, and a writable directory. No server
process, database or container is required (this repo deliberately ships no Docker images or
Kubernetes manifests).

## Schedule

Run **every hour**. A run with nothing new costs ~4 s and 4 small requests (measured), so hourly
polling is cheap while picking up new runs within an hour of their publication:

| source | new run | becomes complete (UTC) |
|---|---|---|
| MEPS | 00/06/12/18Z used on the coast (every 3 h in dev) | nominal + ~2h30 |
| WW3 4 km | 00/06/12/18Z | nominal + ~3h–3h30 |
| NorKyst v3 | 00Z daily | ~06:40 |
| ECMWF 0.25° | 00/12Z | ~07:34 / ~19:34 |

Examples (pick what the platform offers):

```cron
# crontab: minute 10 of every hour
10 * * * * cd /opt/weather-layers && WEATHER_LAYERS_AREA=norway WEATHER_LAYERS_CACHE=0 /usr/local/bin/uv run --project pipeline weather-layers run >> /var/log/weather-layers.jsonl 2>&1
```

```ini
# systemd: weather-layers.service + weather-layers.timer (OnCalendar=*-*-* *:10:00)
[Service]
Type=oneshot
WorkingDirectory=/opt/weather-layers
EnvironmentFile=/etc/weather-layers.env
ExecStart=/usr/local/bin/uv run --project pipeline weather-layers run
```

On a container platform the same command runs as a scheduled job (e.g. a Kubernetes CronJob
with `concurrencyPolicy: Forbid`) built from whatever base image the platform standardises on.
Overlapping runs are also prevented by the pipeline itself (lock file in the state dir; a second
run logs `pipeline.locked` and exits 0).

## Configuration (environment)

| variable | default | notes |
|---|---|---|
| `WEATHER_LAYERS_OUTPUT_DIR` | `data/out` | public files; serve this directory |
| `WEATHER_LAYERS_STATE_DIR` | `data/state` | private per-run series state (+ lock file); not served |
| `WEATHER_LAYERS_CACHE_DIR` | `data/cache` | raw download cache |
| `WEATHER_LAYERS_CACHE` | `auto` | `auto` = on for the dev area only; production fetches each run once, so leave it off |
| `WEATHER_LAYERS_CACHE_MAX_AGE_H` | `48` | cached raw responses older than this are deleted at the start of each run |
| `WEATHER_LAYERS_USER_AGENT` | `weather-layers/<ver> (+https://github.com/egeiran/weather)` | **set to the operator's app name + contact** (MET terms) |
| `WEATHER_LAYERS_AREA` | `dev` | `norway` in production (polygon, decision 0010); also `coast`, `w,s,e,n` or a `.geojson` Polygon |
| `WEATHER_LAYERS_SOURCES` | `meps,wam,norkyst,ecmwf` | |
| `WEATHER_LAYERS_RETENTION` | `2` | runs kept per source; raise to keep history |
| `WEATHER_LAYERS_CONCURRENCY` | `2` | parallel HTTP requests |
| `WEATHER_LAYERS_HTTP_TIMEOUT` / `_MAX_RETRIES` | `120` / `5` | |
| `WEATHER_LAYERS_MEPS_RUN_HOURS` | `auto` | `auto` = 00/06/12/18Z for large areas, all runs for small; or `all`, or `0,6,12,18` |
| `WEATHER_LAYERS_NORKYST_STRIDE` | `auto` | `auto` = 1 (800 m) for small areas, 2 (1.6 km) for the coast |
| `WEATHER_LAYERS_ECMWF_BASE` | AWS open-data mirror | or `https://data.ecmwf.int/forecasts` |
| `WEATHER_LAYERS_ECMWF_MIN_STEP` / `_MAX_STEP` | `48` / `240` | ECMWF steps fetched |
| `WEATHER_LAYERS_SERIES_OCEAN_ONLY` | `auto` | skip inland series chunks on large areas |

## Storage

- Local filesystem is implemented (`storage.LocalStorage`). The host serves `OUTPUT_DIR` as static
  files behind its auth (docs/host-integration.md).
- **Blob storage later:** implement the small `Storage` protocol in `storage.py` (write, atomic
  write, read, list, delete prefix, promote). On blob stores `promote` can be a no-op and runs can
  be written straight to their final prefix: they are only reachable once `manifest.json`, written
  last, references them. Upload `manifest.json` with `Cache-Control: no-cache`, everything else
  immutable.
- Publishing order guarantees readers never see half-written runs: run directories are complete
  before the manifest that references them is replaced (atomic rename locally).

## Sizing

Norway polygon (`norway`, measured 2026-11-27): 942 MB downloaded per full set of runs,
3 min wall time, 156 MB public output (9,004 files), 371 MB state, peak RSS 1.4 GB, **≈ 1.8 GB/day**.
The table below is the larger coast rectangle (`coast`) for comparison; see docs/performance.md.

### Coast rectangle

| | per run | steady state (retention 2) |
|---|---|---|
| public output | ≈ 270 MB, ≈ 17,600 files (MEPS 53 MB, WW3 12 MB, NorKyst 113 MB, ECMWF 5 MB, series 86 MB) | ≈ 0.6 GB |
| private state | ≈ 370 MB | ≈ 0.75 GB |
| download | MEPS 351 MB, WW3 318 MB, NorKyst 1.03 GB, ECMWF 170 MB | ≈ 4 GB/day |
| CPU / memory | 4–5 min wall on an Apple M4; ~2 CPU cores busy; peak RSS 1.1 GB | |

Provision ≥ 2 GB RAM, ≥ 5 GB disk (headroom for retention 3–4), and ~5 GB/day egress from MET/ECMWF.

## Retention

`WEATHER_LAYERS_RETENTION=N` keeps the newest N built runs per source (plus anything the current
or previous manifest still references) and the current and previous point series. Deleting a run
is removing its directory (`runs/<source>/<run_id>` and `state/<source>/<run_id>`). Keeping history
later only means raising N — paths never collide.

## Monitoring

Logs are JSON lines on stderr (`event`, `step`, `duration_s`, `bytes_downloaded`, `bytes_written`,
`files_written`, `requests`, `source`, `run`). Useful alerts:

- **No `pipeline.done` or `publish.noop` for > 2 h** → the job is not running.
- **`source.error`** events, or `manifest.sources.<src>.status` in `stale`/`error`/`missing` for
  > 6 h (MEPS, WW3), > 30 h (NorKyst), > 18 h (ECMWF).
- **Manifest age:** `generated_at` older than the newest expected run + 4 h.
- **Bytes per run** far above the table above → a subsetting regression.
- `weather-layers status` prints a human summary; `weather-layers validate` checks the manifest
  against the schema (run it after deployments).

## Being a good citizen

- Set `WEATHER_LAYERS_USER_AGENT` with a contact; MET blocks anonymous heavy users.
- Keep concurrency low (default 2). The client honours `Retry-After` and backs off exponentially.
- Never point browsers at THREDDS or ECMWF; only this job talks to them, once per model run.
- Further reductions if needed: fetch rotated windows in row bands (WW3, NorKyst: about a third
  less), read NorKyst's netCDF4 files with HDF5 byte ranges (~6× less than OPeNDAP for the
  full grid), or raise `WEATHER_LAYERS_MEPS_RUN_HOURS` to 12-hourly.
