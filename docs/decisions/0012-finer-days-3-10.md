# 0012 — Finer days 3–10: ECMWF 0.1° for wind, MyWaveWAM 3 km for waves and swell

**Status:** accepted (2026-11-27; the owner chose "both" after a comparison with Windy)

## Context
After ~+60 h everything came from ECMWF open data at 0.25° (≈ 12 × 28 km at 63°N). Windy uses
the same ECMWF run at full (~9 km) resolution, so from day 3 its fields were visibly sharper,
and the swell layer ended at +66 h because ECMWF open data has no swell partitions.

## Decision
1. **ECMWF 0.1°** (free since 2026-10-20, CC BY 4.0, same ~9 km run interpolated to 0.1°) is the
   default (`WEATHER_LAYERS_ECMWF_RESOLUTION=0p1`; `0p25` remains available). Files are split
   into `-fc-sfc`/`-pl`; we read `oper/…-fc-sfc` by byte range. It arrives 2 h after the 0.25°
   data (00z ≈ 09:34, 12z ≈ 21:34 UTC).
2. **MyWaveWAM 3 km** (MET Norway, pan-Arctic, the model api.met.no uses beyond ~+66 h) becomes
   the wave and swell source after WW3: new source `wam3`, waves/swell priority
   WW3 (+800 m overlays) → WAM3 → ECMWF. Only the long 18Z runs are used (+234 h; 06Z ends
   at +114 h), from +48 h, every 3 h (`WEATHER_LAYERS_WAM3_MIN_LEAD`, `…_STEP_H`).
3. **ECMWF waves only as a fallback** (`WEATHER_LAYERS_ECMWF_WAVES=auto`: on only when
   `WEATHER_LAYERS_WAM3=0`). This saves the 0.1° wave fields (~6.5 MB per step).
4. A built run counts as built only if its model name and products match the current source
   configuration; otherwise it is rebuilt under the same run id and republished.

## Consequences
- Wind/gusts from day 3 resolve fjords, headlands and lee areas (one zoom level more: z1–4).
- Waves after +66 h follow a 3 km coastline instead of ECMWF's blocky mask; **swell now reaches
  ~day 9** instead of +66 h. Waves end at WAM3's last step (+234 h from 18Z, ≈ 12 h before wind).
- Download for the Norway polygon, measured 2026-11-27: ECMWF 0.1° wind/gust **≈ 504 MB per run**
  (global fields, independent of area; was 170 MB with waves at 0.25°), WAM3 **≈ 153 MB per run**
  (once a day). Daily total ≈ 2.7 → **≈ 3.5 GB/day**. Public output +≈ 20 MB.
- MyWaveWAM 3 km 18Z is ready ≈ 00:30 UTC; ECMWF 0.1° 00z ≈ 09:34 UTC. Until a new ECMWF run is
  complete at 0.1°, the previous run is kept (`pending`).
