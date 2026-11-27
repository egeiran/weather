# 0011 — Nearshore waves: MyWaveWAM 800 m overlays, and one coastline for the whole timeline

**Status:** accepted (2026-11-27; the owner asked for both after seeing "random" wave coverage)

## Context
Where waves have data was decided by each model's own land mask: WW3 4 km treats narrow fjords and
sounds as land, and ECMWF 0.25° (~12 × 28 km) has a blocky mask with straight edges and stray sea
cells deep inside large fjords. The wave layer therefore changed shape at +66 h and looked random.

## Decision
1. **Overlays.** A source can bring higher-resolution grids that replace it wherever they have
   data (`Subset.overlays`). WW3 gets the five MyWaveWAM 800 m coastal grids (newest run per
   domain) for total waves. Values are blended over ~6 native cells (~5 km) at the overlay grid's
   outer edge to avoid seams; where WW3 has no data the overlay is used as is.
2. **Detail zoom only where it matters.** Waves get z6 tiles only around the overlays (a sparse
   pyramid); the client draws the matching part of the parent tile where a child is missing.
3. **One coastline.** WW3's static land/sea mask is saved with each build. For ECMWF waves we keep
   only ECMWF's connected open sea (stray sea cells deep in fjords are dropped), extrapolate one
   ring of cells with the mean of their neighbours, and clip to WW3's coastline, so
   after +66 h the wave layer keeps the same shape (fjords that only the 800 m grids resolve are
   empty again after +66 h: no model resolves them that far ahead).

## Consequences
- Real wave values in fjords and sounds for the first ~66 h where the 800 m grids reach
  (Finnmark, Nord-Norge, Midt-Norge, Vestlandet, Skagerrak; about a quarter of the coastal sea).
- Extra download per WW3 build for the 800 m grids: measured for the Norway polygon 596 MB per
  WW3 build instead of 93 MB (the five grids hold ~640k cells × 67 hours × 3 variables). Swell and
  wind-sea partitions still come from WW3 only.
- Near the coast, ECMWF wave values are extrapolated from the nearest ECMWF sea cell — fine for a
  ~10-day outlook, labelled as ECMWF in the UI.

## Volume choice (owner, 2026-11-27)
Waves (WW3 + 800 m) are fetched from the **00Z and 12Z runs only** for large areas
(`WEATHER_LAYERS_WAM_RUN_HOURS=auto`); small areas take every run. Norway total ≈ 2.7 GB/day
(every 6 h would be ≈ 3.8 GB/day; without the 800 m grids 1.8 GB/day).
