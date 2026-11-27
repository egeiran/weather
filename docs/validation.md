# How we know the map is right

Three independent checks, from "is the pipeline correct?" to "is the forecast good?".

## 1. Same model, same run: MET's own point API (pipeline correctness)

`make crosscheck` → [crosscheck.md](crosscheck.md). Our tiles, decoded at the exact grid point
api.met.no uses, agree with MET's locationforecast/oceanforecast to within rounding:
wind 0.05 m/s and 0.7°, gust 0.06 m/s, current 0.04 kn and 3°, sea temperature 0.04 °C (mean
absolute difference over 8 coastal points × 9 lead times). This proves the chain: fetch,
grid-relative wind rotation, from/to conventions, regridding, 8-bit encoding and decoding.
Waves differ more (0.14 m / 11°) because api.met.no uses WAM 800 m near the coast; we use WW3 4 km.

## 2. Same model, other provider: Windy's ECMWF (stitching and the ECMWF path)

2026-11-27, Windy's point forecast at N63°48'03" E8°18'00" (off Frøya), source ECMWF 9 km /
ECMWF WAM, 3-hourly table read in the browser; ours from the published point series at the same
times (`scripts/windy_compare.py`). Windy shows wind/gusts as whole m/s and waves to 0.1 m.

| ours from | variable | n | bias (ours − Windy) | mean abs diff | max |
|---|---|---:|---:|---:|---:|
| ECMWF 0.25° (days 3–5) | wind | 15 | +0.01 m/s | 0.31 m/s | 0.6 |
| ECMWF 0.25° | gust | 15 | −0.33 m/s | 0.60 m/s | 2.5 |
| ECMWF 0.25° | wave height | 15 | −0.20 m | 0.20 m | 0.3 |
| MEPS 2.5 km (days 0–2.5) | wind | 21 | +0.85 m/s | 1.76 m/s | 4.0 |
| MEPS 2.5 km | gust | 21 | −0.36 m/s | 2.07 m/s | 6.5 |
| WW3 4 km | wave height | 21 | +0.23 m | 0.23 m | 0.5 |
| WW3 4 km | swell height | 21 | +0.47 m | 0.47 m | 1.6 |

Reading it:
- **Where both use ECMWF, they agree to Windy's display rounding** (0.3 m/s, 0.2 m). The small
  wave bias is resolution (our 0.25° open data vs Windy's 9 km).
- **Where we use MEPS, differences of 1–4 m/s are genuine model differences** (e.g. Saturday
  evening ECMWF brings the wind up three hours earlier). MEPS is MET's 2.5 km model, matches
  MET's own forecasts (check 1) and is generally the better model along the Norwegian coast;
  Windy does not offer MEPS.
- **Swell** differs most because the models split swell from wind sea differently (WW3
  partitioning vs ECMWF's definition). After +66 h we show no swell at all (ECMWF open data has
  no swell fields); Windy shows ECMWF swell from its licensed data.

## 3. Against reality (not yet done)

The real test of a forecast is observations (buoys, coastal stations, Barentswatch wave buoys).
MET's observation API (Frost) needs a free client ID, which this project avoids by rule; with the
owner's approval it would allow a standing verification report (forecast vs observed per lead time).
