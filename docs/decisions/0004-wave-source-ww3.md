# 0004 — Waves from WAVEWATCH III 4 km instead of MyWaveWAM 4 km

**Status:** accepted (2026-11-27)

## Context
The brief named MyWaveWAM 4 km (dataset path unknown) with ECMWF waves as the fallback.
The spike found that MyWaveWAM 4 km no longer exists on THREDDS (all paths 404, absent from the
catalog). MET's 4 km regional wave model is now WW3 4 km, documented as such by api.met.no's
oceanforecast data model and ocean.met.no.

## Options
1. WW3 4 km (`ww3_4km_latest_files`): 4 runs/day, hourly to +66 h, hs/tp/dir + wind-sea and swell partitions.
2. MyWaveWAM 800 m: five separate coastal grids, ~25% of the coast area, misses Frøya offshore.
3. ECMWF open-data waves only: 0.25°, 3-hourly, no swell split.

## Decision
WW3 4 km as the regional wave source (source key stays `wam` to match the brief's slot; the UI
label is "WW3"). Swell = partition 1 (`phs1/ptp1/pdir1`), verified to be swell at Frøya (wave age).
ECMWF waves take over after WW3's horizon.

## Consequences
- **No swell gap before +66 h.** After +66 h, swell has no data (ECMWF open data has no partitions).
- Near the coast api.met.no uses WAM 800 m, so the cross-check shows larger wave differences there.
- MyWaveWAM 800 m stays a possible nearshore overlay later.
