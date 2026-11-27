"""Helpers shared by sources on regular projected grids served over OPeNDAP."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np
from pyproj import CRS, Transformer

from ..grids import RegularGrid
from ..mercator import BBox


def bbox_outline(area: BBox, n: int = 50) -> tuple[np.ndarray, np.ndarray]:
    """Points along the bbox edges (projected boxes are not boxes in lat/lon)."""
    t = np.linspace(0.0, 1.0, n)
    lon = np.concatenate(
        [
            area.west + (area.east - area.west) * t,
            np.full(n, area.east),
            area.east - (area.east - area.west) * t,
            np.full(n, area.west),
        ]
    )
    lat = np.concatenate(
        [
            np.full(n, area.south),
            area.south + (area.north - area.south) * t,
            np.full(n, area.north),
            area.north - (area.north - area.south) * t,
        ]
    )
    return lon, lat


def index_window(grid: RegularGrid, area: BBox, margin: int = 2) -> tuple[int, int, int, int]:
    """Index window [j0, j1) x [i0, i1) of `grid` covering `area` (plus a margin).

    Raises ValueError if the area does not intersect the grid.
    """
    lon, lat = bbox_outline(area)
    fi, fj = grid.fractional_index(lon, lat)
    i0 = max(0, math.floor(np.nanmin(fi)) - margin)
    i1 = min(grid.nx, math.ceil(np.nanmax(fi)) + 1 + margin)
    j0 = max(0, math.floor(np.nanmin(fj)) - margin)
    j1 = min(grid.ny, math.ceil(np.nanmax(fj)) + 1 + margin)
    if i1 <= i0 or j1 <= j0:
        raise ValueError("area does not intersect the source grid")
    return j0, j1, i0, i1


def regular_axis(values: np.ndarray, name: str) -> tuple[float, float]:
    """(start, step) of an evenly spaced coordinate axis; raises if it is not regular."""
    v = np.asarray(values, dtype=np.float64)
    d = np.diff(v)
    step = float(np.median(d))
    if not np.allclose(d, step, rtol=1e-4, atol=1e-3 * abs(step)):
        raise ValueError(f"coordinate {name} is not regular (steps {d.min()}..{d.max()})")
    return float(v[0]), step


def cf_crs(attrs: dict) -> CRS:
    """CRS from CF grid_mapping attributes (pyproj understands the CF conventions)."""
    cf = {k: v for k, v in attrs.items() if not k.startswith("_")}
    proj4 = cf.pop("proj4", None) or cf.pop("proj4_string", None)
    try:
        return CRS.from_cf(cf)
    except Exception:
        if proj4:
            return CRS.from_proj4(proj4)
        raise


def epoch_seconds_to_dt(values: np.ndarray) -> list[datetime]:
    return [datetime.fromtimestamp(float(v), tz=UTC) for v in np.asarray(values).ravel()]


def footprint_bbox(grid: RegularGrid) -> BBox:
    """Lon/lat bbox of the grid (from its outline)."""
    xs, ys = grid.x(), grid.y()
    X = np.concatenate([xs, np.full(grid.ny, xs[-1]), xs[::-1], np.full(grid.ny, xs[0])])
    Y = np.concatenate([np.full(grid.nx, ys[0]), ys, np.full(grid.nx, ys[-1]), ys[::-1]])
    tr = Transformer.from_crs(grid.crs, CRS.from_epsg(4326), always_xy=True)
    lon, lat = tr.transform(X, Y)
    return BBox(float(np.min(lon)), float(np.min(lat)), float(np.max(lon)), float(np.max(lat)))
