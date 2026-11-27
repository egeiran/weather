# 0006 — Time stitching and ECMWF usage

**Status:** accepted (2026-11-27)

## Decision
- Per product, sources in priority order: wind → MEPS, ECMWF; waves/swell → WW3, ECMWF; current → NorKyst.
  The first source covers all its valid times; the next only times after the previous one's last time.
  No spatial blending. Tile layers and point series use the same rule (`stitch.py`).
- Each stitched layer is split into **segments** with a constant step (1 h / 3 h / 6 h), each with its
  source, run and label (e.g. "MEPS 06Z", "ECMWF 00Z"). The UI shows segment boundaries.
- ECMWF: 0.25° open data, **00z/12z runs only** (06z/18z end at 144 h); steps **48–240 h**
  (`WEATHER_LAYERS_ECMWF_MIN_STEP`/`MAX_STEP`). 48 h leaves margin if a regional run is up to a day stale.
  ≈ 170 MB per run whatever the area, because open data cannot be spatially subset.
- Fields: `10u/10v`, gust `10fg`/`10fg3` (window recorded), `swh`, `pp1d`, `mwd`.

## Consequences
- Visible resolution change at the MEPS→ECMWF boundary (2.5 km → 0.25°), labelled in the UI.
- ECMWF gusts are maxima over 1/3/6 h windows and can read higher than MEPS's hourly gusts.
