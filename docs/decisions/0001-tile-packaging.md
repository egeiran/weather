# 0001 — Tile packaging: plain XYZ directories of PNG per valid time

**Status:** accepted (2026-11-27)

## Context
Value tiles are served as static files through the host's authenticated proxy (Fleet Tracker
backend), often to thin on-board connections. Criteria: static serving through an auth proxy,
low bandwidth, manageable file counts, easy retention cleanup, MapLibre compatibility.

## Options
1. **XYZ directories** `runs/<source>/<run>/<product>/<time>/<z>/<x>/<y>.png`.
2. **PMTiles per time step** (one archive per product and valid time, read with HTTP Range).
3. One image per time step for the whole area.

## Decision
Option 1, with three measures that keep file counts down:
- **Native max zoom per source** (smallest zoom whose pixel ≤ native spacing at 65°N): MEPS z5,
  WW3 z5, NorKyst z7 (z6 at 1.6 km on the coast), ECMWF z3; min zoom = max − 3. The client over-zooms
  with bilinear interpolation instead of us generating deep zooms.
- **Empty tiles are not written** (e.g. all-land tiles for ocean models). The manifest carries a tiny
  availability bitset per zoom, so the client never requests them (no 404 noise).
- **One run = one directory** → retention is `rm -rf runs/<source>/<run>`.

## Why not PMTiles
- Every host proxy and blob store must support Range requests and pass them through correctly
  (Next.js route handlers do not do this by default). Plain files work with any static handler.
- Range responses cache poorly in browsers and intermediaries. XYZ tiles are immutable per URL
  (the run id is in the path) and can be cached `immutable` for a long time.
- Each time step would need an extra header/directory fetch. Our time steps hold only a handful of
  tiles per view, so this overhead is relatively large.
- We fetch tiles ourselves through the injected fetch, so MapLibre's pmtiles protocol is no advantage.
- File count is the cost: measured in docs/PROGRESS.md / deployment.md (thousands per run, all small).
  If that becomes a problem, the layout maps 1:1 onto PMTiles-per-time-step later (the URL template
  in the manifest is the only thing the client follows).

## Consequences
- Tile URL template is in the manifest; the client substitutes `{time}`, `{z}`, `{x}`, `{y}`.
- Tiles are immutable; the host can send `Cache-Control: public, max-age=31536000, immutable`
  for `runs/**` and `series/**`, and a short max-age for `manifest.json`.
