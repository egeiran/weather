# 0007 — Data volume defaults for the full-coast job ("balanced")

**Status:** accepted (2026-11-27, chosen by the product owner)

## Context
OPeNDAP on thredds.met.no neither compresses responses nor subsets rotated areas, and sends Int16
as 4 bytes. Full-coast, full-resolution, every-run would be ≈ 8.6 GB/day (MEPS 2.8, WW3 1.4,
NorKyst 4.1, ECMWF 0.35).

## Options (presented to the owner)
- Full resolution, all runs: ≈ 8.6 GB/day.
- **Balanced: MEPS 2.5 km 00/06/12/18Z, WW3 every run, NorKyst 1.6 km daily, ECMWF 00/12z: ≈ 3.5 GB/day.**
- Sparse: MEPS 5 km 6-hourly, WW3 12-hourly, NorKyst 1.6 km: ≈ 2.4 GB/day.

## Decision
Balanced, as defaults that switch on only for large areas (the dev area always takes every run at
full resolution):
- `WEATHER_LAYERS_MEPS_RUN_HOURS` (coast default `0,6,12,18`; dev: all).
- `WEATHER_LAYERS_NORKYST_STRIDE=auto` (1 for windows ≤ 1 M cells, else 2 → 1.6 km).

## Consequences
- Coast MEPS is up to 6 h old instead of 3 h. NorKyst coast tiles stop at z6 (1 km/px).
- Further savings (not implemented yet): fetch rotated windows in row bands (−35…−50% for WW3 and
  NorKyst), and HDF5 byte-range reads of NorKyst netCDF4 files (≈ 6× less than OPeNDAP).

## Measured (2026-11-27, full-coast run)
MEPS 351 MB, WW3 318 MB, NorKyst (stride 2) 1.03 GB, ECMWF 170 MB per run → ≈ 4.0 GB/day with
these defaults (the 3.5 GB estimate under-counted WW3's six variables). Row-band fetching is the
next lever if the volume must go down.
