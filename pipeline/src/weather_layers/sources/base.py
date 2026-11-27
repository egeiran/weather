"""Common source interface."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from ..grids import RegularGrid
from ..http import HttpClient
from ..mercator import BBox, native_max_zoom

Fields = dict[str, np.ndarray]


def run_id_of(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y%m%dT%HZ")


def time_key(t: datetime) -> str:
    """Valid-time path segment used in tile URLs, e.g. 20261127T0600Z."""
    return t.astimezone(UTC).strftime("%Y%m%dT%H%MZ")


def iso(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Run:
    source: str
    run_id: str
    reference_time: datetime
    url: str
    valid_times: list[datetime]
    extra: dict = field(default_factory=dict)


@dataclass
class Subset:
    """The data of one run for one area: a regular sub-grid plus a step iterator."""

    grid: RegularGrid
    times: list[datetime]
    steps: Iterator[tuple[int, Fields]]  # (time index, fields at that time on `grid`)
    notes: dict = field(default_factory=dict)
    # Higher-resolution grids that replace the base where they have data (e.g. WAM 800 m).
    overlays: list = field(default_factory=list)
    # Extra zoom levels generated only where overlays exist.
    detail_max_zoom: int | None = None


class Source:
    name: str = ""
    label: str = ""  # short label for the UI, e.g. "MEPS"
    model_name: str = ""  # e.g. "MEPS 2.5 km"
    attribution: str = ""
    license: str = ""
    products: tuple[str, ...] = ()
    nominal_resolution_m: float = 0.0

    def max_zoom(self) -> int:
        """Smallest zoom whose pixels are no larger than the native grid spacing at 65N."""
        return native_max_zoom(self.nominal_resolution_m, 65.0)

    def min_zoom(self) -> int:
        return max(0, self.max_zoom() - 3)

    def configure(self, area_name: str, area: BBox) -> None:
        """Called before discovery; sources may adapt settings to the area size."""

    def latest_complete_run(self, http: HttpClient, is_built=None) -> Run | None:
        raise NotImplementedError

    def fetch(self, http: HttpClient, run: Run, area: BBox) -> Subset:
        raise NotImplementedError

    def describe(self) -> dict:
        return {
            "label": self.label,
            "model": self.model_name,
            "attribution": self.attribution,
            "license": self.license,
        }
