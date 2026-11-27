# MET cross-check

Generated 2026-11-27 11:26 UTC by `weather-layers crosscheck`.
MET values come from api.met.no `locationforecast/2.0/complete` and `oceanforecast/2.0/complete` at 8 coastal points (4-decimal coordinates), at leads 3, 6, 12, 18, 24, 30, 36, 42, 48 h from now. Ours are decoded from the published files (8-bit encoded), in two ways: A from the tiles, B from the click series.

Published runs: MEPS 20261127T06Z, WW3 20261127T06Z, NorKyst 20261127T00Z, ECMWF 20261127T00Z

## A. Tiles at MET's own grid point (pipeline accuracy)

Decoded from the value tiles at the exact coordinates oceanforecast reports for its grid point (locationforecast: the requested point), with the client's bilinear rule.

| variable | unit | n | bias (ours − MET) | mean abs diff | max abs diff | limit | ok |
|---|---|---:|---:|---:|---:|---:|:--:|
| wind_speed | m/s | 72 | -0.01 | 0.05 | 0.19 | 1.5 | yes |
| wind_gust | m/s | 72 | -0.01 | 0.06 | 0.19 | 3.0 | yes |
| wind_from_direction | ° | 69 | -0.22 | 0.68 | 2.46 | 20.0 | yes |
| wave_height | m | 63 | -0.10 | 0.14 | 0.45 | 0.5 | yes |
| wave_from_direction | ° | 63 | -8.44 | 10.71 | 69.51 | 25.0 | yes |
| current_speed | kn | 72 | +0.00 | 0.04 | 0.12 | 0.3 | yes |
| current_to_direction | ° | 47 | -0.29 | 3.01 | 32.68 | 25.0 | yes |
| sea_temperature | °C | 72 | -0.01 | 0.04 | 0.10 | 0.5 | yes |

## B. Click series (what the point panel shows)

Nearest cell of the 0.025° × 0.05° series lattice (≈ 2.8 × 2.4 km), so strong local gradients (currents between islands) differ more than in A.

| variable | unit | n | bias (ours − MET) | mean abs diff | max abs diff | limit | ok |
|---|---|---:|---:|---:|---:|---:|:--:|
| wind_speed | m/s | 72 | -0.11 | 0.21 | 0.90 | 1.5 | yes |
| wind_gust | m/s | 72 | -0.12 | 0.25 | 0.85 | 3.0 | yes |
| wind_from_direction | ° | 69 | -0.56 | 1.57 | 5.12 | 20.0 | yes |
| wave_height | m | 63 | -0.10 | 0.20 | 0.60 | 0.5 | yes |
| wave_from_direction | ° | 63 | -8.62 | 13.49 | 104.43 | 25.0 | yes |
| current_speed | kn | 63 | +0.03 | 0.18 | 0.53 | 0.3 | yes |
| current_to_direction | ° | 45 | +6.13 | 17.11 | 61.59 | 25.0 | yes |
| sea_temperature | °C | 63 | -0.03 | 0.13 | 0.55 | 0.5 | yes |

Direction rows only use times where both magnitudes exceed: wind 3 m/s, waves 0.5 m, current 0.3 kn (directions of calm conditions are undefined).

## Points

| point | requested lat, lon | oceanforecast grid point | locationforecast updated | oceanforecast updated |
|---|---|---|---|---|
| Frøya vest | 63.8000, 8.3000 | 63.7965, 8.2996 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:24Z |
| Sula | 63.8800, 8.5500 | 63.8938, 8.5409 | 2026-11-27T10:28:06Z | 2026-11-27T09:09:30Z |
| Froan | 64.0500, 8.9500 | 64.0479, 8.9656 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:33Z |
| Halten | 64.1500, 9.4500 | 64.1379, 9.4456 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:33Z |
| Frohavet | 63.8500, 9.2000 | 63.8606, 9.2151 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:24Z |
| Hitra sørvest | 63.4500, 7.9000 | 63.4586, 7.9125 | 2026-11-27T10:28:06Z | 2026-11-27T09:09:33Z |
| Grip-retning | 63.4000, 7.6000 | 63.3996, 7.6042 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:30Z |
| Kya | 64.1000, 9.7500 | 64.1025, 9.7490 | 2026-11-27T10:28:19Z | 2026-11-27T09:09:17Z |

## Per-point detail (first lead only)

| point | variable | time | source | ours | MET |
|---|---|---|---|---:|---:|
| Frøya vest | wind_speed | 2026-11-27T14:00:00Z | meps | 3.60 | 3.70 |
| Frøya vest | wind_gust | 2026-11-27T14:00:00Z | meps | 4.75 | 4.80 |
| Frøya vest | wind_from_direction | 2026-11-27T14:00:00Z | meps | 162.35 | 165.00 |
| Frøya vest | wave_height | 2026-11-27T14:00:00Z | wam | 2.80 | 2.80 |
| Frøya vest | wave_from_direction | 2026-11-27T14:00:00Z | wam | 248.47 | 257.40 |
| Frøya vest | current_speed | 2026-11-27T14:00:00Z | norkyst | 0.80 | 0.78 |
| Frøya vest | current_to_direction | 2026-11-27T14:00:00Z | norkyst | 25.41 | 20.40 |
| Frøya vest | sea_temperature | 2026-11-27T14:00:00Z | norkyst | 9.60 | 9.40 |
| Sula | wind_speed | 2026-11-27T14:00:00Z | meps | 3.40 | 3.30 |
| Sula | wind_gust | 2026-11-27T14:00:00Z | meps | 5.00 | 4.60 |
| Sula | wind_from_direction | 2026-11-27T14:00:00Z | meps | 156.71 | 157.00 |
| Sula | wave_height | 2026-11-27T14:00:00Z | wam | 1.60 | 2.10 |
| Sula | wave_from_direction | 2026-11-27T14:00:00Z | wam | 275.29 | 271.00 |
| Sula | current_speed | 2026-11-27T14:00:00Z | norkyst | 0.60 | 0.39 |
| Sula | current_to_direction | 2026-11-27T14:00:00Z | norkyst | 283.76 | 302.70 |
| Sula | sea_temperature | 2026-11-27T14:00:00Z | norkyst | 9.45 | 9.50 |
| Froan | wind_speed | 2026-11-27T14:00:00Z | meps | 6.60 | 6.80 |
| Froan | wind_gust | 2026-11-27T14:00:00Z | meps | 9.00 | 9.20 |
| Froan | wind_from_direction | 2026-11-27T14:00:00Z | meps | 165.18 | 164.00 |
| Froan | wave_height | 2026-11-27T14:00:00Z | wam | 2.10 | 2.00 |
| Froan | wave_from_direction | 2026-11-27T14:00:00Z | wam | 254.12 | 258.70 |
| Froan | current_speed | 2026-11-27T14:00:00Z | norkyst | 0.44 | 0.19 |
| Froan | current_to_direction | 2026-11-27T14:00:00Z | norkyst | 32.47 | 31.00 |
| Froan | sea_temperature | 2026-11-27T14:00:00Z | norkyst | 9.30 | 9.60 |
| Halten | wind_speed | 2026-11-27T14:00:00Z | meps | 8.40 | 8.50 |
| Halten | wind_gust | 2026-11-27T14:00:00Z | meps | 11.00 | 11.00 |
| Halten | wind_from_direction | 2026-11-27T14:00:00Z | meps | 163.76 | 164.00 |
| Halten | wave_height | 2026-11-27T14:00:00Z | wam | 1.20 | 1.10 |
| Halten | wave_from_direction | 2026-11-27T14:00:00Z | wam | 224.47 | 232.80 |
| Halten | current_speed | 2026-11-27T14:00:00Z | norkyst | 0.40 | 0.19 |
| Halten | current_to_direction | 2026-11-27T14:00:00Z | norkyst | 43.76 | 345.60 |
| Halten | sea_temperature | 2026-11-27T14:00:00Z | norkyst | 9.45 | 9.20 |
| Frohavet | wind_speed | 2026-11-27T14:00:00Z | meps | 8.40 | 9.00 |
| Frohavet | wind_gust | 2026-11-27T14:00:00Z | meps | 11.25 | 12.00 |
| Frohavet | wind_from_direction | 2026-11-27T14:00:00Z | meps | 138.35 | 141.00 |
| Frohavet | wave_height | 2026-11-27T14:00:00Z | wam | 0.80 | 1.00 |
| Frohavet | wave_from_direction | 2026-11-27T14:00:00Z | wam | 142.59 | 228.10 |
| Frohavet | current_speed | 2026-11-27T14:00:00Z | norkyst | 0.96 | 0.78 |
| Frohavet | current_to_direction | 2026-11-27T14:00:00Z | norkyst | 306.35 | 318.30 |
| Frohavet | sea_temperature | 2026-11-27T14:00:00Z | norkyst | 8.85 | 8.90 |
| Hitra sørvest | wind_speed | 2026-11-27T14:00:00Z | meps | 2.60 | 2.80 |
| Hitra sørvest | wind_gust | 2026-11-27T14:00:00Z | meps | 3.75 | 3.90 |
| Hitra sørvest | wind_from_direction | 2026-11-27T14:00:00Z | meps | 145.41 | 152.00 |
| Grip-retning | wind_speed | 2026-11-27T14:00:00Z | meps | 3.00 | 3.40 |
| Grip-retning | wind_gust | 2026-11-27T14:00:00Z | meps | 4.25 | 4.70 |
| Grip-retning | wind_from_direction | 2026-11-27T14:00:00Z | meps | 166.59 | 163.00 |
| Grip-retning | wave_height | 2026-11-27T14:00:00Z | wam | 3.10 | 2.90 |
| Grip-retning | wave_from_direction | 2026-11-27T14:00:00Z | wam | 245.65 | 246.10 |
| Grip-retning | current_speed | 2026-11-27T14:00:00Z | norkyst | 0.24 | 0.19 |
| Grip-retning | current_to_direction | 2026-11-27T14:00:00Z | norkyst | 21.18 | 22.10 |
| Grip-retning | sea_temperature | 2026-11-27T14:00:00Z | norkyst | 9.45 | 9.40 |
| Kya | wind_speed | 2026-11-27T14:00:00Z | meps | 7.00 | 7.30 |
| Kya | wind_gust | 2026-11-27T14:00:00Z | meps | 9.25 | 9.40 |
| Kya | wind_from_direction | 2026-11-27T14:00:00Z | meps | 151.06 | 155.00 |
| Kya | wave_height | 2026-11-27T14:00:00Z | wam | 0.80 | 0.90 |
| Kya | wave_from_direction | 2026-11-27T14:00:00Z | wam | 272.47 | 275.10 |
| Kya | current_speed | 2026-11-27T14:00:00Z | norkyst | 0.16 | 0.00 |
| Kya | current_to_direction | 2026-11-27T14:00:00Z | norkyst | 83.29 | 328.40 |
| Kya | sea_temperature | 2026-11-27T14:00:00Z | norkyst | 8.85 | 9.10 |
