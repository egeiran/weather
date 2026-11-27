# Performance and sizes (measured 2026-11-27)

Measured with `scripts/perf.mjs` in headless Chromium on the real GPU (ANGLE Metal, Apple M4),
1440×900 CSS px at device pixel ratio 2, against the Vite demo server (no HTTP compression).
"Step change" = everything fetched between two settled states when pressing *next step*,
including the background prefetch of the following step; average of three steps.

## Budget

| | budget | measured worst case |
|---|---|---|
| First view, one layer | ≤ ~1.5 MB | 398 KB (wind, whole coast, incl. 44 KB manifest) |
| Time-step change | ≤ ~300 KB | 177 KB (wind, whole coast) |
| Click for values | ≤ ~2 small requests | 1 request, 7–11 KB |
| Particles | ~60 fps on a laptop | 60 fps in every scenario |

## Full-coast data (57.5–71.5°N, 4–31.5°E)

| scenario | first view | step change (avg of 3) | click | fps (particles) |
|---|---|---|---|---:|
| wind, whole coast z4.4 | 398 KB in 9 req, 1.5 s | 177 KB in 4.0 req | inland: no series (0 req) | 60 |
| waves, whole coast z4.4 | 135 KB in 9 req, 1.3 s | 46 KB in 4.0 req | inland: no series (0 req) | 60 |
| current, whole coast z4.4 | 170 KB in 7 req, 1.4 s | 64 KB in 3.0 req | inland: no series (0 req) | 60 |
| wind, Mid-Norway z7 | 318 KB in 5 req, 1.6 s | 137 KB in 2.0 req | 11 KB in 1 req | 60 |
| current, Mid-Norway z7 | 315 KB in 13 req, 1.7 s | 137 KB in 6.0 req | 11 KB in 1 req | 60 |
| waves, Lofoten z8 | 75 KB in 3 req, 1.6 s | 15 KB in 1.0 req | 9 KB in 1 req | 60 |

## Development area (Frøya/Hitra)

| scenario | first view | step change (avg of 3) | click | fps (particles) |
|---|---|---|---|---:|
| wind z8.3 | 40 KB in 1 req, 1.9 s | 8 KB in 1.7 req | 7 KB in 1 req | 60 |
| waves z8.3 | 44 KB in 3 req, 1.5 s | 2 KB in 1.0 req | 7 KB in 1 req | 60 |
| current z8.3 | 121 KB in 5 req, 1.5 s | 40 KB in 2.0 req | 7 KB in 1 req | 60 |

## Full-coast pipeline run

`weather-layers run --area coast` with an empty cache, balanced defaults (decision 0007), on an
Apple M4 laptop over home broadband:

| source (run) | downloaded | wall time | written | files |
|---|---:|---:|---:|---:|
| MEPS 2.5 km (06Z) | 351 MB | 43 s | 53 MB | 1,341 |
| WW3 4 km (06Z) | 318 MB | 31 s | 12 MB | 1,207 |
| NorKyst v3 (00Z, 1.6 km stride) | 1,027 MB | 163 s | 113 MB | 5,083 |
| ECMWF 0.25° (00Z, steps 48–240) | 170 MB | 29 s | 4.6 MB | 589 |
| merged point series | – | 8 s | 86 MB | 9,410 |
| **total** | **1.87 GB** | **4 min 42 s** | **268 MB public + 371 MB state** | **17,631** |

- Peak memory (max RSS): 1.1 GB.
- A rerun with nothing new: **4.3 s, 4 requests, 12 KB** downloaded, nothing written.
- With retention 2, steady-state disk ≈ 2 × (public + state) ≈ 1.3 GB.

### Daily volume with the balanced defaults

| source | runs/day | per run | per day |
|---|---:|---:|---:|
| MEPS | 4 (00/06/12/18Z) | 351 MB | 1.4 GB |
| WW3 | 4 | 318 MB | 1.3 GB |
| NorKyst | 1 | 1.03 GB | 1.0 GB |
| ECMWF | 2 | 170 MB | 0.34 GB |
| **total** | | | **≈ 4.0 GB** |

The estimate given when choosing the default (≈ 3.5 GB) assumed WW3 at 57 MB per variable × 4;
measured WW3 is 318 MB per run. Fetching rotated windows in row bands would cut WW3 and NorKyst
by about a third (not implemented; see deployment.md).
