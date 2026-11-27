# 0002 — Value encoding: three 8-bit linear channels in an RGB PNG, 258×258

**Status:** accepted (2026-11-27)

## Context
Ramps and thresholds must change on the client without regenerating tiles, so tiles carry values,
not colours. Precision targets: wind/gust ≤ 0.2 m/s, wave height ≤ 0.05 m, period ≤ 0.1 s,
current ≤ 0.02 kn, direction ≤ 2°. Browsers premultiply alpha when decoding images, so alpha must
not carry data.

## Options
- 16-bit u/v pairs (or 12+12 bits packed into RGB): high precision, but noisy low bytes compress
  badly (2–3× larger PNGs) and decoding is fiddly.
- **8 bits per quantity, linear `value = offset + scale·code`, code 255 = no data.**

## Decision
8-bit linear channels; each product puts three quantities in R, G, B (alpha absent, PNG colour type 2):

| product | R | G | B |
|---|---|---|---|
| wind | speed, 0.2 m/s steps (0–50.8) | direction FROM, 360/255° | gust, 0.25 m/s (0–63.5) |
| waves | Hs, 0.1 m (0–25.4) | peak period, 0.1 s (0–25.4) | mean direction FROM |
| swell | swell Hs, 0.1 m | swell period, 0.1 s | swell direction FROM |
| current | speed, 0.04 kn (0–10.16) | direction TO | sea temperature, 0.15 °C from −3 |

Max quantisation error = scale/2: wind 0.1 m/s, gust 0.125 m/s, Hs 0.05 m, period 0.05 s,
current 0.02 kn, direction 0.71°. All within targets (tested in `test_encoding.py`).

Vectors are stored as **speed + direction**, not u/v: this meets both the speed and the direction
targets with 8 bits each, where 8-bit u/v cannot reach 2° at low speeds. The client turns each of
the four bilinear taps into a vector before interpolating, so directions interpolate correctly
across 0/360.

Tiles are 256 px + a 1-px border (258×258) holding the neighbours' samples, so the client can do
manual bilinear interpolation inside one texture with no seams at tile edges.

## Consequences
- Values above the range clip to the max code (documented per channel in the manifest `max`).
- The client samples with NEAREST and decodes in the shader; images are decoded with
  `premultiplyAlpha: 'none'` and `colorSpaceConversion: 'none'`; PNGs carry no gAMA/iCCP/sRGB chunks.
