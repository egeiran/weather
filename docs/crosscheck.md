# MET cross-check

Generated 2026-11-27 10:54 UTC by `weather-layers crosscheck`.
Our values are the decoded point series (what a click returns: nearest lattice cell, 8-bit encoded). MET values come from api.met.no `locationforecast/2.0/complete` and `oceanforecast/2.0/complete` at the same coordinates (4 decimals), at leads 3, 6, 12, 18, 24, 30, 36, 42, 48 h from now.

Published runs: MEPS 20261127T06Z, WW3 20261127T06Z, NorKyst 20261127T00Z, ECMWF 20261127T00Z

## A. Tiles at MET's own grid point (pipeline accuracy)

Decoded from the value tiles at the exact coordinates oceanforecast reports for its grid point (locationforecast: the requested point), with the client's bilinear rule.

| variable | unit | n | bias (ours − MET) | mean abs diff | max abs diff | limit | ok |
|---|---|---:|---:|---:|---:|---:|:--:|
| wind_speed | m/s | 72 | -0.01 | 0.05 | 0.20 | 1.5 | yes |
| wind_gust | m/s | 72 | -0.03 | 0.06 | 0.23 | 3.0 | yes |
| wind_from_direction | ° | 68 | -0.01 | 0.92 | 7.46 | 20.0 | yes |
| wave_height | m | 63 | -0.10 | 0.14 | 0.39 | 0.5 | yes |
| wave_from_direction | ° | 63 | -8.10 | 9.96 | 78.69 | 25.0 | yes |
| current_speed | kn | 72 | +0.01 | 0.05 | 0.13 | 0.3 | yes |
| current_to_direction | ° | 42 | -0.43 | 2.87 | 26.42 | 25.0 | yes |
| sea_temperature | °C | 72 | +0.00 | 0.04 | 0.10 | 0.5 | yes |

## B. Click series (what the point panel shows)

Nearest cell of the 0.025° × 0.05° series lattice (≈ 2.8 × 2.4 km), so strong local gradients (currents between islands) differ more than in A.

| variable | unit | n | bias (ours − MET) | mean abs diff | max abs diff | limit | ok |
|---|---|---:|---:|---:|---:|---:|:--:|
| wind_speed | m/s | 72 | -0.09 | 0.21 | 0.70 | 1.5 | yes |
| wind_gust | m/s | 72 | -0.11 | 0.24 | 1.05 | 3.0 | yes |
| wind_from_direction | ° | 68 | -0.48 | 1.72 | 5.35 | 20.0 | yes |
| wave_height | m | 63 | -0.10 | 0.18 | 0.50 | 0.5 | yes |
| wave_from_direction | ° | 63 | -8.20 | 12.66 | 112.75 | 25.0 | yes |
| current_speed | kn | 63 | +0.04 | 0.19 | 0.49 | 0.3 | yes |
| current_to_direction | ° | 41 | +3.02 | 17.13 | 65.72 | 25.0 | yes |
| sea_temperature | °C | 63 | -0.02 | 0.13 | 0.60 | 0.5 | yes |

Direction rows only use times where both magnitudes exceed: wind 3 m/s, waves 0.5 m, current 0.3 kn (directions of calm conditions are undefined).

## Points

| point | requested lat, lon | oceanforecast grid point | locationforecast updated | oceanforecast updated |
|---|---|---|---|---|
| Frøya vest | 63.8000, 8.3000 | 63.7965, 8.2996 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:24Z |
| Sula | 63.8800, 8.5500 | 63.8938, 8.5409 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:33Z |
| Froan | 64.0500, 8.9500 | 64.0479, 8.9656 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:30Z |
| Halten | 64.1500, 9.4500 | 64.1379, 9.4456 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:24Z |
| Frohavet | 63.8500, 9.2000 | 63.8606, 9.2151 | 2026-11-27T10:28:06Z | 2026-11-27T09:09:33Z |
| Hitra sørvest | 63.4500, 7.9000 | 63.4586, 7.9125 | 2026-11-27T10:28:06Z | 2026-11-27T09:09:17Z |
| Grip-retning | 63.4000, 7.6000 | 63.3996, 7.6042 | 2026-11-27T10:28:06Z | 2026-11-27T09:09:24Z |
| Kya | 64.1000, 9.7500 | 64.1025, 9.7490 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:33Z |

## Per-point detail (first lead only)

| point | variable | time | source | ours | MET |
|---|---|---|---|---:|---:|
| Frøya vest | wind_speed | 2026-11-27T13:00:00Z | meps | 3.40 | 3.20 |
| Frøya vest | wind_gust | 2026-11-27T13:00:00Z | meps | 4.50 | 4.30 |
| Frøya vest | wind_from_direction | 2026-11-27T13:00:00Z | meps | 156.71 | 157.00 |
| Frøya vest | wave_height | 2026-11-27T13:00:00Z | wam | 2.70 | 2.70 |
| Frøya vest | wave_from_direction | 2026-11-27T13:00:00Z | wam | 248.47 | 259.30 |
| Frøya vest | current_speed | 2026-11-27T13:00:00Z | norkyst | 0.92 | 0.97 |
| Frøya vest | current_to_direction | 2026-11-27T13:00:00Z | norkyst | 28.24 | 22.70 |
| Frøya vest | sea_temperature | 2026-11-27T13:00:00Z | norkyst | 9.60 | 9.50 |
| Sula | wind_speed | 2026-11-27T13:00:00Z | meps | 3.60 | 3.30 |
| Sula | wind_gust | 2026-11-27T13:00:00Z | meps | 5.25 | 4.90 |
| Sula | wind_from_direction | 2026-11-27T13:00:00Z | meps | 156.71 | 157.00 |
| Sula | wave_height | 2026-11-27T13:00:00Z | wam | 1.50 | 2.00 |
| Sula | wave_from_direction | 2026-11-27T13:00:00Z | wam | 276.71 | 273.70 |
| Sula | current_speed | 2026-11-27T13:00:00Z | norkyst | 0.32 | 0.19 |
| Sula | current_to_direction | 2026-11-27T13:00:00Z | norkyst | 289.41 | 332.10 |
| Sula | sea_temperature | 2026-11-27T13:00:00Z | norkyst | 9.45 | 9.50 |
| Froan | wind_speed | 2026-11-27T13:00:00Z | meps | 7.00 | 7.10 |
| Froan | wind_gust | 2026-11-27T13:00:00Z | meps | 9.75 | 9.90 |
| Froan | wind_from_direction | 2026-11-27T13:00:00Z | meps | 162.35 | 161.00 |
| Froan | wave_height | 2026-11-27T13:00:00Z | wam | 2.00 | 1.90 |
| Froan | wave_from_direction | 2026-11-27T13:00:00Z | wam | 254.12 | 258.50 |
| Froan | current_speed | 2026-11-27T13:00:00Z | norkyst | 0.48 | 0.39 |
| Froan | current_to_direction | 2026-11-27T13:00:00Z | norkyst | 52.24 | 86.90 |
| Froan | sea_temperature | 2026-11-27T13:00:00Z | norkyst | 9.30 | 9.60 |
| Halten | wind_speed | 2026-11-27T13:00:00Z | meps | 8.40 | 8.50 |
| Halten | wind_gust | 2026-11-27T13:00:00Z | meps | 11.00 | 11.00 |
| Halten | wind_from_direction | 2026-11-27T13:00:00Z | meps | 162.35 | 162.00 |
| Halten | wave_height | 2026-11-27T13:00:00Z | wam | 1.20 | 1.10 |
| Halten | wave_from_direction | 2026-11-27T13:00:00Z | wam | 220.24 | 218.60 |
| Halten | current_speed | 2026-11-27T13:00:00Z | norkyst | 0.40 | 0.19 |
| Halten | current_to_direction | 2026-11-27T13:00:00Z | norkyst | 57.88 | 10.40 |
| Halten | sea_temperature | 2026-11-27T13:00:00Z | norkyst | 9.45 | 9.30 |
| Frohavet | wind_speed | 2026-11-27T13:00:00Z | meps | 8.80 | 9.40 |
| Frohavet | wind_gust | 2026-11-27T13:00:00Z | meps | 11.75 | 12.40 |
| Frohavet | wind_from_direction | 2026-11-27T13:00:00Z | meps | 135.53 | 140.00 |
| Frohavet | wave_height | 2026-11-27T13:00:00Z | wam | 0.90 | 1.00 |
| Frohavet | wave_from_direction | 2026-11-27T13:00:00Z | wam | 136.94 | 188.90 |
| Frohavet | current_speed | 2026-11-27T13:00:00Z | norkyst | 0.88 | 0.78 |
| Frohavet | current_to_direction | 2026-11-27T13:00:00Z | norkyst | 304.94 | 321.10 |
| Frohavet | sea_temperature | 2026-11-27T13:00:00Z | norkyst | 8.85 | 8.90 |
| Hitra sørvest | wind_speed | 2026-11-27T13:00:00Z | meps | 2.80 | 3.00 |
| Hitra sørvest | wind_gust | 2026-11-27T13:00:00Z | meps | 3.75 | 3.90 |
| Hitra sørvest | wind_from_direction | 2026-11-27T13:00:00Z | meps | 146.82 | 152.00 |
| Grip-retning | wind_speed | 2026-11-27T13:00:00Z | meps | 2.20 | 2.20 |
| Grip-retning | wind_gust | 2026-11-27T13:00:00Z | meps | 4.25 | 4.30 |
| Grip-retning | wind_from_direction | 2026-11-27T13:00:00Z | meps | 206.12 | 207.00 |
| Grip-retning | wave_height | 2026-11-27T13:00:00Z | wam | 2.90 | 2.80 |
| Grip-retning | wave_from_direction | 2026-11-27T13:00:00Z | wam | 245.65 | 246.40 |
| Grip-retning | current_speed | 2026-11-27T13:00:00Z | norkyst | 0.28 | 0.19 |
| Grip-retning | current_to_direction | 2026-11-27T13:00:00Z | norkyst | 32.47 | 35.20 |
| Grip-retning | sea_temperature | 2026-11-27T13:00:00Z | norkyst | 9.45 | 9.40 |
| Kya | wind_speed | 2026-11-27T13:00:00Z | meps | 7.00 | 7.20 |
| Kya | wind_gust | 2026-11-27T13:00:00Z | meps | 9.50 | 9.60 |
| Kya | wind_from_direction | 2026-11-27T13:00:00Z | meps | 149.65 | 155.00 |
| Kya | wave_height | 2026-11-27T13:00:00Z | wam | 0.80 | 0.90 |
| Kya | wave_from_direction | 2026-11-27T13:00:00Z | wam | 273.88 | 272.60 |
| Kya | current_speed | 2026-11-27T13:00:00Z | norkyst | 0.20 | 0.00 |
| Kya | current_to_direction | 2026-11-27T13:00:00Z | norkyst | 86.12 | 60.30 |
| Kya | sea_temperature | 2026-11-27T13:00:00Z | norkyst | 8.85 | 9.10 |
