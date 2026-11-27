"""Synthetic sources for offline end-to-end tests (no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
from pyproj import CRS

from weather_layers.grids import RegularGrid
from weather_layers.mercator import BBox
from weather_layers.sources.base import Run, Source, Subset, run_id_of

LCC = CRS.from_proj4("+proj=lcc +lat_0=63.3 +lon_0=15 +lat_1=63.3 +lat_2=63.3 +R=6371000")


class FakeMeps(Source):
    name = "meps"
    label = "MEPS"
    model_name = "fake MEPS"
    attribution = "MET Norway"
    license = "test"
    products = ("wind",)
    nominal_resolution_m = 10000.0

    def __init__(self, runs: list[datetime], fail: bool = False, steps: int = 4):
        self.runs = runs
        self.fail = fail
        self.steps = steps
        self.fetches = 0

    def latest_complete_run(self, http, is_built=None):
        ref = max(self.runs)
        return Run(
            self.name,
            run_id_of(ref),
            ref,
            "fake://meps",
            [ref + timedelta(hours=h) for h in range(self.steps)],
        )

    def fetch(self, http, run, area: BBox) -> Subset:
        self.fetches += 1
        if self.fail:
            raise RuntimeError("source down")
        # 10 km grid covering the dev area generously
        grid = RegularGrid(LCC.to_wkt(), -500000.0, 10000.0, 60, -100000.0, 10000.0, 40, 10000.0)

        def steps():
            for t in range(len(run.valid_times)):
                u = np.full((grid.ny, grid.nx), 5.0 + t, dtype=np.float32)
                v = np.zeros_like(u)
                yield t, {"wind_u": u, "wind_v": v, "wind_gust": u * 1.5}

        return Subset(grid, run.valid_times, steps())


class FakeNorKyst(FakeMeps):
    name = "norkyst"
    label = "NorKyst"
    products = ("current",)

    def fetch(self, http, run, area):
        self.fetches += 1
        grid = RegularGrid(LCC.to_wkt(), -500000.0, 10000.0, 60, -100000.0, 10000.0, 40, 10000.0)

        def steps():
            for t in range(len(run.valid_times)):
                u = np.full((grid.ny, grid.nx), 0.5, dtype=np.float32)
                u[:, 30:] = np.nan  # land on the east half
                yield t, {"current_u": u, "current_v": u * 0, "sea_temperature": u * 0 + 8}

        return Subset(grid, run.valid_times, steps())


def t(day: int, hour: int) -> datetime:
    return datetime(2026, 11, day, hour, tzinfo=UTC)
