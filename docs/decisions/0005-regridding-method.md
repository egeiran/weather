# 0005 — Regridding: pyproj forward transform + fractional index + NaN-aware bilinear

**Status:** accepted (2026-11-27)

## Context
Grids: MEPS Lambert conformal, NorKyst polar stereographic, WW3 rotated lat/lon, ECMWF lat/lon.
Output: Web Mercator tiles. No GDAL.

## Decision
All four grids are regular in their own CRS. For each output pixel, transform lon/lat → grid CRS
with pyproj, compute fractional indices `(x − x0)/dx`, `(y − y0)/dy` and interpolate bilinearly.
The 2-D lat/lon arrays are never treated as regular (and are not even downloaded).
- **No data:** NaN corners are dropped and the remaining weights renormalised; a pixel is valid if
  ≥ 50% of its weight lies on valid cells, which puts the coastline halfway between sea and land cells.
- **Vectors** are rotated to true east/north on the native grid (MEPS) and interpolated as components;
  wave directions as unit vectors. Speed/direction are computed after interpolation.
- **Anti-aliasing at low zooms:** if a tile pixel spans k ≥ 2 native cells, the field is first
  block-averaged k×k (NaN-aware).
- Sampling weights are precomputed once per tile and reused for every time step.
- Every source is clipped to the area's lat/lon box, so all layers cover the same rectangle.

## Consequences
- Tested: linear fields are reproduced exactly at arbitrary points; cell centres return cell values;
  no-data and out-of-domain handling; periodic longitudes.
- A truly curvilinear grid without a grid mapping would need another method (KD-tree inversion).
  None of our sources needs it.
