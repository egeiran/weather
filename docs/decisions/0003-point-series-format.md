# 0003 — Point series: merged WLS1 chunks on a global 0.025°×0.05° lattice

**Status:** accepted (2026-11-27)

## Context
A click must show all related values plus a time series over the whole stitched timeline and the
first threshold exceedance, at a cost of at most ~2 small HTTP requests on a thin connection.
Four sources with different grids and timelines are involved.

## Options
1. Per-source chunk files → 4 requests per click.
2. Decode values from the tiles the client already has → only the current time, no series.
3. **One merged file per chunk of cells, all variables, all times, rebuilt at every publish.**

## Decision
Option 3.
- Lattice: cells of 0.025° lat × 0.05° lon (≈ 2.8 × 2.4 km at 64°N) aligned to (−90°, −180°);
  chunks of 4×4 cells (0.1° × 0.2°). Chunk indices are global, so the client finds the file from
  lat/lon alone: `cy = floor((lat+90)/0.1)`, `cx = floor((lon+180)/0.2)`.
- File `series/<id>/<cy>/<cx>.bin`: gzip of `b"WLS1"` + uint16 LE rows, cols, nvars, ntimes +
  uint8 codes `[var][row][col][time]` (rows south→north). Same 8-bit encodings as the tiles; the
  variable list, encodings, stitched time axis and per-variable source segments are in the manifest.
- Cell values: bilinear from the native grid at the cell centre. For ocean products the coast rule is
  relaxed (any valid neighbour counts), so a coastal click borrows the nearest sea value instead of
  returning "no data".
- Chunks without any data are not written; an availability bitset is in the manifest.
- The series id hashes the set of source runs; unchanged sets are not rebuilt.

## Consequences
- One click = one request of ≈ 9 KB (dev measurement: 12 variables × 145 times × 16 cells).
- Rebuilt at each publish (~every 3–6 h) from per-run state arrays kept outside the public dir
  (`data/state`), as memory-mapped `.npy`.
- Series values can differ slightly from the colour field under the cursor (different sampling
  lattice, nearest-sea borrowing). The click panel labels the cell position.
- The client decompresses with `DecompressionStream('gzip')` and tolerates proxies that already
  removed the gzip layer (checks the magic bytes).

## Addendum (after the full-coast run)
For large areas (`WEATHER_LAYERS_SERIES_OCEAN_ONLY=auto`, > 200k lattice cells) only chunks that
contain ocean-model data are written: inland Sweden/Finland is irrelevant for the fleet and would
add ~10k files per publish. Coastal clicks still work (chunks are 11 × 10 km and coastal cells
borrow the nearest sea value). Measured on the coast: 9,410 chunks, 86 MB per publish, 9–11 KB per click.
