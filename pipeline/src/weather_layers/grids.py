"""Source grids and resampling to Web Mercator tiles.

Every source grid we use is *regular in some CRS* (MEPS: Lambert conformal; NorKyst: polar
stereographic; WAM: rotated lat/lon; ECMWF: plain lat/lon). We therefore never treat the 2-D
lat/lon arrays as regular: for each target pixel we transform lon/lat into the grid's own CRS
with pyproj and compute fractional indices, then interpolate bilinearly. No-data (NaN) is
handled by renormalising the weights of the valid corners; a point is valid when at least
half of its interpolation weight falls on valid cells, which puts the coastline half-way
between the last sea cell and the first land cell.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np
from pyproj import CRS, Transformer

from . import mercator

WGS84 = CRS.from_epsg(4326)


@dataclass(frozen=True)
class RegularGrid:
    """x[i] = x0 + i*dx, y[j] = y0 + j*dy in `crs` units (dy may be negative)."""

    crs_wkt: str
    x0: float
    dx: float
    nx: int
    y0: float
    dy: float
    ny: int
    resolution_m: float
    periodic_lon: bool = False  # global lat/lon grid wrapping in longitude

    @property
    def crs(self) -> CRS:
        return CRS.from_wkt(self.crs_wkt)

    def x(self) -> np.ndarray:
        return self.x0 + self.dx * np.arange(self.nx)

    def y(self) -> np.ndarray:
        return self.y0 + self.dy * np.arange(self.ny)

    def subset(self, j0: int, j1: int, i0: int, i1: int) -> RegularGrid:
        """Sub-grid for index ranges [j0, j1) x [i0, i1)."""
        return replace(
            self,
            x0=self.x0 + i0 * self.dx,
            nx=i1 - i0,
            y0=self.y0 + j0 * self.dy,
            ny=j1 - j0,
            periodic_lon=False,
        )

    def coarsen(self, k: int) -> RegularGrid:
        if k <= 1:
            return self
        return replace(
            self,
            x0=self.x0 + (k - 1) / 2 * self.dx,
            dx=self.dx * k,
            nx=self.nx // k,
            y0=self.y0 + (k - 1) / 2 * self.dy,
            dy=self.dy * k,
            ny=self.ny // k,
            resolution_m=self.resolution_m * k,
        )

    def fractional_index(self, lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        tr = _transformer(self.crs_wkt)
        X, Y = tr.transform(np.asarray(lon, dtype=np.float64), np.asarray(lat, dtype=np.float64))
        X = np.asarray(X)
        if self.periodic_lon or self.crs.is_geographic:
            X = self.x0 + np.mod(X - self.x0 + (0.5 * self.dx), 360.0) - 0.5 * self.dx
        return (X - self.x0) / self.dx, (np.asarray(Y) - self.y0) / self.dy

    def lonlat(self) -> tuple[np.ndarray, np.ndarray]:
        """2-D lon/lat of the grid cell centres."""
        X, Y = np.meshgrid(self.x(), self.y())
        tr = Transformer.from_crs(self.crs, WGS84, always_xy=True)
        lon, lat = tr.transform(X, Y)
        return np.asarray(lon), np.asarray(lat)


_TRANSFORMERS: dict[str, Transformer] = {}


def _transformer(crs_wkt: str) -> Transformer:
    tr = _TRANSFORMERS.get(crs_wkt)
    if tr is None:
        tr = Transformer.from_crs(WGS84, CRS.from_wkt(crs_wkt), always_xy=True)
        _TRANSFORMERS[crs_wkt] = tr
    return tr


def coarsen_field(field: np.ndarray, k: int, min_valid_fraction: float = 0.5) -> np.ndarray:
    """Block-mean over k x k cells of the last two axes, NaN-aware."""
    if k <= 1:
        return field
    *lead, ny, nx = field.shape
    ny2, nx2 = ny // k, nx // k
    f = field[..., : ny2 * k, : nx2 * k].reshape(*lead, ny2, k, nx2, k)
    valid = np.isfinite(f)
    count = valid.sum(axis=(-3, -1))
    total = np.where(valid, f, 0.0).sum(axis=(-3, -1))
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / count
    out[count < min_valid_fraction * k * k] = np.nan
    return out.astype(np.float32)


@dataclass
class Sampler:
    """Precomputed bilinear sampling of a RegularGrid at arbitrary lon/lat points."""

    i0: np.ndarray
    j0: np.ndarray
    wx: np.ndarray
    wy: np.ndarray
    inside: np.ndarray
    shape: tuple[int, ...]

    @classmethod
    def build(cls, grid: RegularGrid, lon: np.ndarray, lat: np.ndarray) -> Sampler:
        fi, fj = grid.fractional_index(lon, lat)
        inside = (fi >= -0.5) & (fi <= grid.nx - 0.5) & (fj >= -0.5) & (fj <= grid.ny - 0.5)
        inside &= np.isfinite(fi) & np.isfinite(fj)
        fi = np.clip(np.nan_to_num(fi), 0, grid.nx - 1)
        fj = np.clip(np.nan_to_num(fj), 0, grid.ny - 1)
        i0 = np.clip(np.floor(fi).astype(np.int64), 0, max(grid.nx - 2, 0))
        j0 = np.clip(np.floor(fj).astype(np.int64), 0, max(grid.ny - 2, 0))
        wx = np.clip(fi - i0, 0.0, 1.0).astype(np.float32)
        wy = np.clip(fj - j0, 0.0, 1.0).astype(np.float32)
        return cls(i0, j0, wx, wy, inside, np.shape(lon))

    def sample(self, field: np.ndarray, min_weight: float = 0.5) -> np.ndarray:
        """Sample field[..., ny, nx] -> [..., *shape]. NaN marks no data."""
        i0, j0 = self.i0, self.j0
        i1 = np.minimum(i0 + 1, field.shape[-1] - 1)
        j1 = np.minimum(j0 + 1, field.shape[-2] - 1)
        wx, wy = self.wx, self.wy
        corners = (
            (field[..., j0, i0], (1 - wx) * (1 - wy)),
            (field[..., j0, i1], wx * (1 - wy)),
            (field[..., j1, i0], (1 - wx) * wy),
            (field[..., j1, i1], wx * wy),
        )
        num = np.zeros(field.shape[:-2] + self.shape, dtype=np.float32)
        den = np.zeros_like(num)
        for values, w in corners:
            ok = np.isfinite(values)
            num += np.where(ok, values, 0.0) * w
            den += np.where(ok, w, 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            out = num / den
        out[(den < min_weight - 1e-6) | ~np.broadcast_to(self.inside, out.shape)] = np.nan
        return out


def zoom_coarsen_factor(grid: RegularGrid, z: int, lat: float) -> int:
    """How many native cells fit in one tile pixel at zoom z (>= 1), for anti-aliasing."""
    return max(1, int(math.floor(mercator.pixel_size_m(z, lat) / grid.resolution_m)))
