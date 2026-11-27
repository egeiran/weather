"""The global lat/lon lattice used for point series.

Cells are DLAT x DLON degrees, aligned to (-90, -180). Chunks group CHUNK x CHUNK cells and
are the unit the client downloads on click (one small request per click). Rows run south to
north, columns west to east. The same formulas live in web/layer/src/core/series.ts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .mercator import BBox

DLAT = 0.025
DLON = 0.05
CHUNK = 4


@dataclass(frozen=True)
class SeriesWindow:
    """A chunk-aligned window of the lattice: rows r0..r0+ny-1, cols c0..c0+nx-1."""

    r0: int
    c0: int
    ny: int
    nx: int

    @classmethod
    def for_area(cls, area: BBox) -> SeriesWindow:
        r0 = math.floor((area.south + 90.0) / DLAT / CHUNK) * CHUNK
        r1 = math.ceil((area.north + 90.0) / DLAT / CHUNK) * CHUNK
        c0 = math.floor((area.west + 180.0) / DLON / CHUNK) * CHUNK
        c1 = math.ceil((area.east + 180.0) / DLON / CHUNK) * CHUNK
        return cls(r0, c0, r1 - r0, c1 - c0)

    def lonlat(self) -> tuple[np.ndarray, np.ndarray]:
        """2-D (ny, nx) cell-centre lon/lat."""
        lat = -90.0 + (self.r0 + np.arange(self.ny) + 0.5) * DLAT
        lon = -180.0 + (self.c0 + np.arange(self.nx) + 0.5) * DLON
        lon2, lat2 = np.meshgrid(lon, lat)
        return lon2, lat2

    def to_manifest(self) -> dict:
        return {
            "origin": [-180.0, -90.0],
            "dlon": DLON,
            "dlat": DLAT,
            "chunk": CHUNK,
            "row0": self.r0,
            "col0": self.c0,
            "rows": self.ny,
            "cols": self.nx,
        }

    def intersect(self, other: SeriesWindow):
        """Overlap as (rows slice in self, cols slice in self, rows in other, cols in other)."""
        r0 = max(self.r0, other.r0)
        r1 = min(self.r0 + self.ny, other.r0 + other.ny)
        c0 = max(self.c0, other.c0)
        c1 = min(self.c0 + self.nx, other.c0 + other.nx)
        if r1 <= r0 or c1 <= c0:
            return None
        return (
            slice(r0 - self.r0, r1 - self.r0),
            slice(c0 - self.c0, c1 - self.c0),
            slice(r0 - other.r0, r1 - other.r0),
            slice(c0 - other.c0, c1 - other.c0),
        )


def cell_of(lon: float, lat: float) -> tuple[int, int]:
    return math.floor((lat + 90.0) / DLAT), math.floor((lon + 180.0) / DLON)
