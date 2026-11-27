# 0010 — Areas of any shape: polygons, fetched in a few strips

**Status:** accepted (2026-11-27; the owner chose "Norway + its sea" for production)

## Context
The coast rectangle (57.5–71.5°N, 4–31.5°E) is mostly Sweden, Finland and the Baltic. OPeNDAP
can only cut rectangles (index hyperslabs), so a shape has to be fetched as several rectangles.

## Decision
- An area is a box plus an optional polygon (`BBox.polygon`). Named: `dev` and `coast` (boxes),
  `norway` (polygon around mainland Norway and its sea, ~15 km into the neighbours, sea
  ~100–250 km offshore; 31 % of the coast rectangle). Custom: `w,s,e,n` or a GeoJSON Polygon file.
- Sources fetch the area in **row strips**, each spanning only the columns whose cells fall
  inside the polygon (+3 cells). MEPS and WW3 store one chunk per whole field, so the server reads
  every chunk once per strip: they use **4 strips** (MEPS fetches 38 % of the window, WW3 29 %).
  NorKyst is chunked in 24-row blocks: **48-row strips** (53 %). ECMWF has no subsetting.
- Tiles and point-series cells outside the polygon are no-data; tiles that end up empty are not written.
- The manifest publishes the polygon in `area.polygon`.

## Consequences (measured, Norway polygon vs coast rectangle, balanced defaults)
| | rectangle | Norway polygon |
|---|---:|---:|
| MEPS / WW3 / NorKyst / ECMWF per run | 351 / 318 / 1,027 / 170 MB | 133 / 93 / 545 / 170 MB |
| total per run, wall time | 1.87 GB, 4 min 42 s | 942 MB, 3 min |
| published output | 268 MB, 17,631 files | 156 MB, 9,004 files |
| per day | ≈ 4.0 GB | ≈ 1.8 GB |

More strips would save a little more bandwidth but multiply server reads (20 strips ≈ 20×);
4 is the polite balance. The polygon is deliberately coarse: it only decides what is fetched
and drawn, the coastline itself comes from the models' land masks.
