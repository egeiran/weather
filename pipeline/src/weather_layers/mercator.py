"""Web Mercator (EPSG:3857) XYZ tile math.

Tiles are 256x256 data pixels plus a BUFFER-pixel border on each side (so 258x258 images with
BUFFER=1). The border holds the neighbouring tiles' samples, which lets the client interpolate
bilinearly inside one texture without seams at tile edges.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

TILE_SIZE = 256
BUFFER = 1
IMAGE_SIZE = TILE_SIZE + 2 * BUFFER
MAX_LAT = 85.0511287798066
EARTH_CIRCUMFERENCE_M = 2 * math.pi * 6378137.0


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def as_list(self) -> list[float]:
        return [self.west, self.south, self.east, self.north]


def lonlat_to_mercator01(lon: np.ndarray | float, lat: np.ndarray | float):
    """Lon/lat (deg) -> normalised mercator X, Y in [0, 1] (Y grows southwards)."""
    lat_c = np.clip(lat, -MAX_LAT, MAX_LAT)
    x = (np.asarray(lon) + 180.0) / 360.0
    y = 0.5 - np.log(np.tan(np.pi / 4 + np.radians(lat_c) / 2)) / (2 * np.pi)
    return x, y


def mercator01_to_lonlat(x: np.ndarray | float, y: np.ndarray | float):
    lon = np.asarray(x) * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * np.asarray(y)))))
    return lon, lat


def tile_range(bbox: BBox, z: int) -> tuple[int, int, int, int]:
    """Inclusive tile index range (x0, x1, y0, y1) covering bbox at zoom z."""
    n = 2**z
    x0, y0 = lonlat_to_mercator01(bbox.west, bbox.north)
    x1, y1 = lonlat_to_mercator01(bbox.east, bbox.south)
    eps = 1e-9
    return (
        max(0, int(math.floor(float(x0) * n))),
        min(n - 1, int(math.floor(float(x1) * n - eps))),
        max(0, int(math.floor(float(y0) * n))),
        min(n - 1, int(math.floor(float(y1) * n - eps))),
    )


def tile_pixel_lonlat(z: int, x: int, y: int) -> tuple[np.ndarray, np.ndarray]:
    """Pixel-centre longitudes (per column) and latitudes (per row) of a buffered tile image.

    Mercator tiles are separable: longitude depends only on the column, latitude only on the
    row. Returns (lon[IMAGE_SIZE], lat[IMAGE_SIZE]).
    """
    n = 2**z
    idx = (np.arange(IMAGE_SIZE, dtype=np.float64) - BUFFER + 0.5) / TILE_SIZE
    mx = (x + idx) / n
    my = (y + idx) / n
    lon, _ = mercator01_to_lonlat(mx, 0.0)
    _, lat = mercator01_to_lonlat(0.0, my)
    return np.asarray(lon), np.asarray(lat)


def tile_bounds(z: int, x: int, y: int) -> BBox:
    n = 2**z
    west, north = mercator01_to_lonlat(x / n, y / n)
    east, south = mercator01_to_lonlat((x + 1) / n, (y + 1) / n)
    return BBox(float(west), float(south), float(east), float(north))


def pixel_size_m(z: int, lat: float) -> float:
    """Ground size (m) of one data pixel at zoom z (256-px tiles) and latitude."""
    return EARTH_CIRCUMFERENCE_M * math.cos(math.radians(lat)) / (TILE_SIZE * 2**z)


def native_max_zoom(resolution_m: float, lat: float, oversample: float = 1.0) -> int:
    """Smallest zoom whose pixel is <= resolution/oversample at `lat` (cap at 12)."""
    for z in range(0, 13):
        if pixel_size_m(z, lat) <= resolution_m / oversample:
            return z
    return 12
