"""Vector rotation and direction conventions.

Conventions used throughout the project:
- (u, v) are always TRUE east/north components of the *motion* (where the air/water moves to).
- Meteorological direction ("from"), used for wind and waves: the compass bearing the wind or
  waves come FROM, clockwise from north. Wind blowing towards the south-west comes from NE (45).
- Oceanographic direction ("to"), used for currents: the bearing the water flows TOWARDS.
"""

from __future__ import annotations

import numpy as np
from pyproj import CRS, Transformer

KNOTS_PER_MS = 3600.0 / 1852.0


def speed(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    return np.hypot(u, v)


def to_direction(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bearing (deg, 0..360) the flow goes TO, clockwise from north."""
    return np.mod(np.degrees(np.arctan2(u, v)), 360.0)


def from_direction(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Bearing (deg, 0..360) the flow comes FROM (meteorological convention)."""
    return np.mod(to_direction(u, v) + 180.0, 360.0)


def uv_from_to_direction(spd: np.ndarray, to_deg: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rad = np.radians(to_deg)
    return spd * np.sin(rad), spd * np.cos(rad)


def uv_from_from_direction(spd: np.ndarray, from_deg: np.ndarray):
    return uv_from_to_direction(spd, np.asarray(from_deg) + 180.0)


def grid_north_angle(crs: CRS, x: np.ndarray, y: np.ndarray, eps: float = 100.0) -> np.ndarray:
    """Angle (radians) of the grid +x axis relative to true east, counter-clockwise positive.

    Computed by finite differences through the projection, so it works for any projected grid
    (Lambert conformal, polar stereographic, rotated pole). x, y are 2-D projected coordinates.
    """
    to_ll = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
    lon0, lat0 = to_ll.transform(x - eps / 2, y)
    lon1, lat1 = to_ll.transform(x + eps / 2, y)
    dlon = np.radians(((np.asarray(lon1) - np.asarray(lon0) + 180.0) % 360.0) - 180.0)
    d_east = dlon * np.cos(np.radians((np.asarray(lat0) + np.asarray(lat1)) / 2))
    d_north = np.radians(np.asarray(lat1) - np.asarray(lat0))
    return np.arctan2(d_north, d_east)


def rotate_grid_to_earth(gx: np.ndarray, gy: np.ndarray, alpha: np.ndarray):
    """Rotate grid-relative components (along grid x, y) to true east/north.

    `alpha` is the grid x-axis angle from east (counter-clockwise), see grid_north_angle.
    Assumes a conformal grid (y-axis perpendicular to x-axis), true for LCC/stereographic.
    """
    ca, sa = np.cos(alpha), np.sin(alpha)
    u = gx * ca - gy * sa
    v = gx * sa + gy * ca
    return u, v
