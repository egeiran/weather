# Data sources

Everything below was verified live against the servers on **2026-11-27**. All sources are free,
keyless and need no account. The pipeline talks to them only through `pipeline/src/weather_layers/http.py`
(identifying User-Agent, capped concurrency, backoff on 429/5xx, raw cache in development).

| Layer(s) | Source (key) | Model | Grid | Steps / horizon | Runs, lag |
|---|---|---|---|---|---|
| Wind, gusts (days 0–2.5) | `meps` | MEPS 2.5 km deterministic | Lambert conformal, 2.5 km | 1 h, +0…+66 h (67) | every 3 h; ~2h30 after nominal |
| Waves, swell (days 0–2.5) | `wam` | **WAVEWATCH III 4 km** (replaces MyWaveWAM 4 km) | rotated lat/lon 0.04° (~4.4 km) | 1 h, +0…+66 h (67 of 73) | 00/06/12/18Z; ~3–3.5 h |
| Current, sea temperature | `norkyst` | **NorKyst v3 800 m** (replaces NorKyst800 v2) | polar stereographic, 800 m | 1 h, +0…+120 h (121) | daily 00Z; complete ~06:40 UTC |
| Waves, swell (days ~3–10) | `wam3` | MyWaveWAM 3 km (pan-Arctic) | rotated lat/lon 0.03° (~3 km) | 3 h (of 1 h), +48…+234 h | 18Z used; ~00:30 UTC |
| Wind, gusts (days ~3–10) | `ecmwf` | ECMWF IFS open data **0.1°** (0.25° optional) | regular lat/lon 0.1° | 3 h to +144 h, 6 h to +240 h | 00/12Z; ~09:34 / 21:34 UTC |

Attribution shown in the UI: **"MET Norway"** and **"ECMWF"** (plus the basemap's).

---

## MEPS 2.5 km (wind, gusts)

- **Catalog:** `https://thredds.met.no/thredds/catalog/mepslatest/catalog.xml` (8 runs ≈ 24 h kept).
- **OPeNDAP:** `https://thredds.met.no/thredds/dodsC/mepslatest/meps_det_2_5km_<YYYYMMDD>T<HH>Z.ncml`.
  OPeNDAP is the only service that works (NCSS returns 503; the THREDDS `latest.xml` resolver returns 500).
- **Latest complete run:** regex over the catalog, newest first; accept if `time` has 67 steps and
  `wind_speed[66][0][500][500]` is not the fill value. No partial runs were observed (all steps of a
  run are written within ~1 min, then the NcML appears), but the check stays.
- **Variables** (`Float32 [time=67][height7=1][y=1069][x=949]`, `_FillValue 9.96921e36`, no packing):
  `x_wind_10m`, `y_wind_10m` (standard_name `x_wind`/`y_wind` = **grid-relative**), `wind_speed`,
  `wind_direction` (standard_name `wind_from_direction`), `wind_speed_of_gust`, `x_wind_gust_10m`, `y_wind_gust_10m`.
  We fetch `x_wind_10m`, `y_wind_10m`, `wind_speed_of_gust`. The height dimension name differs
  between datasets (`height7` here, `height6` in the archive), so code never hard-codes it.
- **Grid:** `projection_lambert`: `lambert_conformal_conic`, `standard_parallel 63.3,63.3`,
  `longitude_of_central_meridian 15`, `latitude_of_projection_origin 63.3`, `earth_radius 6371000`
  ≙ `+proj=lcc +lat_0=63.3 +lon_0=15 +lat_1=63.3 +lat_2=63.3 +R=6371000`. `x`: −1060084…1309916 m,
  `y`: −1332517.875…1337482.125 m, both 2500 m, **y ascending (row 0 = south)**.
- **Vector convention (verified):** rotate grid → earth with γ = sin(63.3°)·(lon − 15°):
  `u_east = x·cosγ + y·sinγ`, `v_north = −x·sinγ + y·cosγ`. Against MET's own `wind_direction`
  over 7,693 samples the rotated direction differs by ≤ 0.053°; unrotated is off by up to 32.6°.
  The pipeline computes the angle per cell by finite differences through pyproj (`vectors.grid_north_angle`),
  which equals the analytic convergence to < 0.05° (tested).
- **Domain:** 49.8–75.1°N, −17.8–53.5°E: fully contains the coast area (margins ≥ 133 cells).
  Dev window ≈ 55×60 cells; coast window 657×656 cells.
- **Payload** (no HTTP compression on `.dods`; checked with gzip/deflate): dev ≈ 2.7 MB per run
  (3 variables × 67 steps); coast ≈ 115 MB per variable per run ≈ **347 MB per run**.
  With the default "balanced" setting the coast job takes only the 00/06/12/18Z runs (≈ 1.4 GB/day).
- **Quirks:** brackets in constraints must be percent-encoded (`%5B`/`%5D`), else HTTP 400;
  the same variable may not appear twice in one constraint; `var.var[...]` returns the array without maps.

## Waves: WAVEWATCH III 4 km (in place of MyWaveWAM 4 km)

**MyWaveWAM 4 km no longer exists on THREDDS** (`fou-hi/mywavewam4*` → 404, not in the catalog tree).
MET's 4 km regional wave model is now WW3 4 km (forced by MEPS and ECMWF winds), which is what
api.met.no oceanforecast uses outside the 800 m coastal WAM domains. See decision 0004.

- **Catalog:** `https://thredds.met.no/thredds/catalog/ww3_4km_latest_files/catalog.xml` (≈ 45 runs, 11 days).
- **OPeNDAP:** `https://thredds.met.no/thredds/dodsC/ww3_4km_latest_files/ww3_<YYYYMMDD>T<HH>Z.nc`
  (match `^ww3_\d{8}T\d{2}Z\.nc$`; the folder also holds spectra files).
  Avoid the aggregation `ww3_4km_agg`: it lags a run and stops at +47 h.
- **Latest complete run:** accept if `len(time) == 73`, `time[72] == frt + 66 h` and `hs[72][450][340]` is finite.
- **Time:** 73 hourly steps from frt−6 h to frt+66 h; **lead 0 is index 6**. We use indices 6…72.
- **Variables** (`Float32 [time=73][rlat=1026][rlon=624]`, `_FillValue -999`, land = NaN):
  `hs` (m), `tp` (peak period, s), `dir` (mean direction, **from**), wind sea = partition 0
  (`phs0`, `ptp0`, `pdir0`), **swell = partition 1** (`phs1`, `ptp1`, `pdir1`, from). Absent
  partitions are NaN over sea too, so the land mask comes from `hs` (static in time).
- **Grid:** `rotated_pole`: `rotated_latitude_longitude`, `grid_north_pole_longitude 140`,
  `grid_north_pole_latitude 22`, `earth_radius 6371000`; `rlon` 5.53…30.45, `rlat` −14.35…26.65, step 0.04°.
  Grid north is 40–45° east of true north along the coast; directions in the file are already true.
- **Domain:** covers the coast area except an inland corner (≈ 57.5–58°N, > 29°E).
- **Payload:** dev ≈ 3 MB per run (6 variables); coast ≈ 57 MB per variable per run ≈ 340 MB per run.

**MyWaveWAM 800 m** is used as a nearshore **overlay** on WW3 (decision 0011): five coastal grids
(`fou-hi/mywavewam800{f,n,m,v,s}_curr/MyWave_wam800_curr_c{0..4}WAVE{HH}.nc`, ring buffer per cycle
hour, ~4–4.5 h lag; rotated lat/lon 0.008°; 73 hourly steps frt−6 h…+66 h; `forecast_reference_time`
in days). We take `hs`, `tp` and `thq` (direction **towards**, converted to "from"); land is
`−9999999` (_FillValue). Where a grid has data it replaces WW3 for total waves (height, period,
direction), blended over ~5 km at the grid edge, and tiles get one extra zoom level (z6) there.
It reaches into fjords and sounds WW3 4 km cannot resolve; it covers about a quarter of the coastal sea.

**MyWaveWAM 3 km** pan-Arctic (to +234 h) is what api.met.no uses after +66 h; ECMWF covers that
range for us. ECMWF's 0.25° wave field is extrapolated over its own blocky land mask and clipped to
WW3's coastline, so the wave layer keeps the same coastline through the whole timeline.

## NorKyst v3 800 m (current, sea temperature)

The NorKyst800 **v2** aggregate (`sea/norkyst800m/1h/aggregate_be`) is listed as discontinued
(production ended 2025-10-01; last time 2025-10-10). The current product is NorKyst v3.

- **OPeNDAP:** `https://thredds.met.no/thredds/dodsC/fou-hi/norkystv3_800m_m00_be` (best-estimate aggregate
  since 2024-01-01; per-run files under `fou-hi/norkystv3_his_files/YYYY/MM/DD/`).
- **Runs:** daily 00Z, +0…+120 h hourly (121 steps). First 24 h ready ≈ 04:30 UTC, full run ≈ 06:40 UTC.
- **Latest complete run:** N = `len(time)` from the `.dds`; fetch `forecast_reference_time` and
  `time[N−121:N−1]`; complete iff `time[N−121] == frt`, `time[N−1] == frt + 120 h` and steps are 3600 s.
  Never compute indices from dates (the axis has gaps in 2024). Because the aggregate URL is
  stable while its content changes, raw-cache keys are namespaced by run and index.
- **Variables** (`Int16 [time][depth=15][Y=1148][X=2747]`, ×0.001, `_FillValue -32767` = land):
  `u_eastward`, `v_northward` (**true east/north**, "going to"; v3 has no grid-relative u/v),
  `temperature` (offset +10 °C), `zeta`. Depth index 0 = 0 m. DAP sends Int16 as 4 bytes.
- **Grid:** `projection_stere`: polar stereographic on **WGS84** (`+proj=stere +lat_0=90 +lat_ts=60
  +lon_0=70 +x_0=3369600 +y_0=1844800 +a=6378137 +b=6356752.3142`), X 0…2196800, Y 0…917600, exactly 800 m.
- **Domain:** the whole Norwegian coast from the Skagerrak to Kola; not inland Sweden/Finland and not the
  far offshore corner at 69–71.5°N west of ~5–8°E. Currents have **no ECMWF fallback**: the layer ends at +120 h.
- **Payload:** dev ≈ 19 MB per variable per run (≈ 60 MB for u, v, temperature). Coast at full
  resolution ≈ 1.37 GB per variable per run; the default coast setting fetches every 2nd cell
  (1.6 km, `WEATHER_LAYERS_NORKYST_STRIDE`, ≈ 1 GB per run). HDF5 byte-range reads of the netCDF4
  files would be ~6× cheaper for the full grid (not implemented; see deployment.md).
- **Verified against api.met.no oceanforecast:** identical values (direction within 0.05°) for 112 hours at Frøya.

## MyWaveWAM 3 km (waves and swell, days ~3–10)

- **Where:** `https://thredds.met.no/thredds/catalog/fou-hi/mywavewam3_latest/catalog.xml`,
  files `MyWave_wam3_WAVE_<YYYYMMDD>T<HH>Z.nc` (last 3 days kept), OPeNDAP like the other MET models.
- **Runs:** 06Z (133 hourly steps, to +114 h) and 18Z (253 hourly steps, frt−18 h … frt+234 h,
  ready ≈ 6.5 h after nominal time). We use the newest **18Z** run (`MIN_STEPS` 240), from +48 h
  (`WEATHER_LAYERS_WAM3_MIN_LEAD`), every 3 h (`WEATHER_LAYERS_WAM3_STEP_H`). Completeness: the
  last step must have values.
- **Grid:** rotated lat/lon (pole lon 140°, lat 25°), 0.03° (~3 km), 1995 × 2379, pan-Arctic; the
  whole `norway` polygon lies inside it (checked). Land = `_FillValue` −9999999.
- **Fields:** `hs`, `tp`, `thq` (mean direction **towards**), `hs_swell`, `tp_swell`, `thq_swell`
  (towards) → we add 180° for "from". `forecast_reference_time` is in **days** since 1970.
- **Payload (Norway polygon, 4 strips, 63 steps × 6 variables):** ≈ 153 MB per run, one run a day.
- **Licence:** CC BY 4.0 (MET Norway). This is the model api.met.no uses for waves after ~+66 h.

## ECMWF IFS open data 0.1° (wind and gusts, days ~3–10)

- **Licence:** CC BY 4.0 + ECMWF terms. Open data comes at **0.1°** (since 2026-10-20, published
  2 h after the 0.25°) and 0.25°, both interpolated from the same ~9 km run; the native grid needs
  a paid agreement. Default 0.1° (`WEATHER_LAYERS_ECMWF_RESOLUTION=0p1|0p25`, decision 0012).
- **Files:** `<base>/YYYYMMDD/HHz/ifs/0p1/{oper|wave}/YYYYMMDDHH0000-<step>h-{oper|wave}-fc-sfc.grib2`
  (0.25°: `ifs/0p25/…-fc.grib2`) + `.index` (JSON lines with `param`, `levtype`, `_offset`,
  `_length`). Default base is the AWS open-data mirror
  `https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com` (`WEATHER_LAYERS_ECMWF_BASE` can point at
  `https://data.ecmwf.int/forecasts`). Byte ranges per field; no spatial subsetting exists.
- **Runs/steps:** 00z/12z: 0–144 h every 3 h, 150–360 h every 6 h. 06z/18z stop at 144 h → unused.
  A run is uploaded in one batch; the completeness marker is the last object (`…-360h-wave-…index`).
  0.1° release: 00z ≈ 09:34, 12z ≈ 21:34 UTC.
- **Fields:** `10u`, `10v`; gust `10fg` (max of last **1 h** for steps ≤ 90), `10fg3` (last 3 h,
  steps 93–144), `10fg` (last 6 h, ≥ 150) — the window is recorded in `run.json` notes.
  Waves (`swh`, `pp1d`, `mwd` "from") only as a fallback when MyWaveWAM 3 km is switched off
  (`WEATHER_LAYERS_ECMWF_WAVES=auto|1|0`); open data has no swell partitions.
- **Decoding:** `eccodes` + `eccodeslib` wheels (Apache-2.0, bundles libaec/OpenJPEG) — no Homebrew.
  Packing `grid_ccsds`; 0.1° grid 3600×1801 (0.25°: 1440×721), row 0 = 90°N, first column = 180°
  (→ lon −180…179.9). Wave fields have a bitmap (land, big lakes) → NaN.
- **Payload:** 0.1° ≈ 3–3.7 MB per global wind/gust field; steps 48–240 (49 steps × 3 fields)
  ≈ **504 MB per run**, 2 runs/day, for any area size (0.25° with waves was ≈ 170 MB).

## Area tuning

- MEPS covers everything; WW3 misses only an inland corner; NorKyst covers the coastal sea but not the far
  offshore NW corner nor inland. The coast area therefore stays 57.5–71.5°N, 4–31.5°E; inland parts are
  simply "no data" for ocean layers (transparent) and are skipped as tiles.

## Known gaps

- **Waves end ≈ 12 h before wind:** MyWaveWAM 3 km 18Z reaches +234 h; ECMWF wind +240 h.
- **Currents after +120 h:** no free model beyond NorKyst v3 in this pipeline.
- **Gust windows differ:** MEPS hourly gust vs ECMWF 1/3/6 h maxima — later ECMWF gusts are maxima over longer windows.
- **Fjords after +66 h:** the 800 m wave grids end at +66 h; MyWaveWAM 3 km resolves wider fjords only.

## Licences and credit

- MET Norway: NLOD 2.0 and CC BY 4.0 — "Based on data from MET Norway"
  (<https://www.met.no/en/free-meteorological-data/Licensing-and-crediting>).
- ECMWF: CC BY 4.0 — "This service is based on data and products of the European Centre for
  Medium-Range Weather Forecasts (ECMWF)", source www.ecmwf.int, CC BY 4.0 link, ECMWF's liability
  disclaimer, and a note that the data was modified (regridded and tiled). Full wording in `docs/contract.md`.
- Basemap: OpenFreeMap (© OpenMapTiles, © OpenStreetMap contributors).
