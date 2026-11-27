# 0009 — Particles: own WebGL2 custom layer in the webgl-wind style

**Status:** accepted (2026-11-27)

## Context
Animated particles like Windy, on MapLibre GL JS 6 (WebGL2 custom layers with
`prerender`/`render` hooks), without heavy dependencies (deck.gl), switchable, off for
`prefers-reduced-motion` and slow connections, ~60 fps on a laptop.

## Decision
Own implementation inside the single weather custom layer:
- A **vector target** (half-resolution RGBA8, screen-aligned) is rendered from the visible value
  tiles each frame: normalised east/north motion + validity. Arrows and particles both sample it,
  so ocean layers never animate over land.
- **Particle state** in two RGBA8 textures (16-bit fixed-point x/y in screen uv), advected on the
  GPU with the map's bearing taken into account; random respawn (drop rate grows with speed),
  respawn outside the data. 1,500–12,000 particles depending on screen area.
- **Trails** in a ping-pong texture faded by 0.93 per frame, composited in `render`; cleared when the
  camera moves (positions are screen-space).
- Motion: wind speed (m/s), current speed (kn), waves move at the deep-water phase speed 1.56·T.
- `particles: 'auto' | true | false`; 'auto' turns them off for `prefers-reduced-motion: reduce`
  and `navigator.connection.saveData` or `effectiveType` in {slow-2g, 2g, 3g}.

## Consequences
- Measured 60 fps (Apple M4, 1440×900 @2x) in every scenario; headless CI uses SwiftShader where
  trails look shorter.
- Globe projection is not supported (mercator matrices only); the host uses mercator.
