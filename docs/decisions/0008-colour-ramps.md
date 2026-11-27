# 0008 — Colour ramps: sequential, colour-blind safe families; "calm" by default

**Status:** accepted as default (2026-11-27); the owner was shown the three families side by side
(artifact "Værlagets utseende") and can switch with `rampFamily` at any time.

## Context
Ramps must read on both OpenFreeMap styles (positron light, dark), work for colour-blind
viewers (no red/green-only distinctions) and keep the host's vessels and sites readable.

## Options
- **calm**: per-kind single-hue-ish ramps (wind blue→violet, waves aqua→indigo, period lavender,
  current cream→teal) with opacity rising from 0.3 to 0.82.
- **vivid**: Crameri "batlow"-like multi-hue (Windy feel), opacity 0.62–0.85.
- **viridis**: viridis / cividis / mako, opacity 0.6–0.8.

## Decision
Default `calm`. All three are sequential with monotonic lightness (unit-tested), interpolated in
OKLab, and rendered client-side from a 256×1 texture, so switching needs no new tiles. Value stops
are non-linear per layer (finer at low values, e.g. waves 0, 0.25, 0.5, 1, 1.5, 2, … 8 m).
Threshold marking is separate (hatching, with tint and contour-only as options) and picks a light
or dark stroke from the luminance of the field underneath, so it reads on every ramp and both maps.

## Consequences
- Low values are deliberately faint in `calm`; calm weather does not dominate the map.
- The legend shows the ramp opaque with ticks spaced ≥ 11 % apart and the threshold marker.
