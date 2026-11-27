"""MEPS 2.5 km deterministic (MET Norway / MetCoOp): 10 m wind and gusts.

Facts (verified live 2026-11-27, see docs/data-sources.md):
- Catalog https://thredds.met.no/thredds/catalog/mepslatest/catalog.xml lists
  meps_det_2_5km_<YYYYMMDD>T<HH>Z.ncml; OPeNDAP at .../dodsC/mepslatest/<name>.
- New run every 3 h, published ~2h30 after nominal time; 67 hourly steps (+0..+66 h).
- Lambert conformal grid, 2500 m, x/y in metres, y ascending (row 0 = south).
- x_wind_10m/y_wind_10m are GRID-RELATIVE (standard_name x_wind/y_wind). We rotate them to
  true east/north; verified against MET's wind_direction to < 0.06 deg.
"""

from __future__ import annotations

import math
import os
import re
from collections.abc import Iterator

import numpy as np

from ..dap import DapDataset
from ..grids import RegularGrid
from ..http import HttpClient, HttpError
from ..log import log
from ..mercator import BBox
from ..vectors import grid_north_angle, rotate_grid_to_earth
from .base import Fields, Run, Source, Subset, run_id_of
from .projected import (
    band_stats,
    cf_crs,
    epoch_seconds_to_dt,
    index_window,
    plan_bands,
    regular_axis,
    steps_per_request,
)

CATALOG = "https://thredds.met.no/thredds/catalog/mepslatest/catalog.xml"
DODS_BASE = "https://thredds.met.no/thredds/dodsC/mepslatest/"
NAME_RE = re.compile(r"meps_det_2_5km_(\d{8})T(\d{2})Z\.ncml")
EXPECTED_STEPS = 67


class Meps(Source):
    name = "meps"
    label = "MEPS"
    model_name = "MEPS 2.5 km (MET Norway)"
    attribution = "MET Norway"
    license = "CC BY 4.0 / NLOD"
    products = ("wind",)
    nominal_resolution_m = 2500.0

    def __init__(self, cache: bool = True) -> None:
        self.cache = cache
        self.run_hours: set[int] | None = None  # None = every run

    def configure(self, area_name: str, area: BBox) -> None:
        env = os.environ.get("WEATHER_LAYERS_MEPS_RUN_HOURS", "auto").strip()
        if env == "auto":
            # Decision 0007 ("balanced"): large areas take only 00/06/12/18Z.
            big = (area.east - area.west) * (area.north - area.south) > 50
            self.run_hours = {0, 6, 12, 18} if big else None
        elif env in ("", "all"):
            self.run_hours = None
        else:
            self.run_hours = {int(h) for h in env.split(",")}

    # -- discovery ------------------------------------------------------------------------
    def candidates(self, http: HttpClient) -> list[str]:
        xml = http.get(CATALOG).text
        names = sorted({m.group(0) for m in NAME_RE.finditer(xml)}, reverse=True)
        if self.run_hours is not None:
            names = [n for n in names if int(NAME_RE.match(n).group(2)) in self.run_hours]
        return names

    def latest_complete_run(self, http: HttpClient, is_built=None) -> Run | None:
        for name in self.candidates(http)[:4]:
            m = NAME_RE.match(name)
            assert m
            run_id = f"{m.group(1)}T{m.group(2)}Z"
            url = DODS_BASE + name
            if is_built is not None and is_built(run_id):
                return self._run(run_id, url, None)
            try:
                ds = DapDataset(http, url, cache=False)
                time_decl = ds.variables.get("time")
                n = time_decl.shape[0] if time_decl else 0
                if n < EXPECTED_STEPS:
                    log("source.incomplete", source=self.name, run=run_id, steps=n)
                    continue
                probe = ds.fetch(
                    {
                        "forecast_reference_time": "",
                        "time": f"[0:{n - 1}]",
                        "wind_speed": f"[{n - 1}][0][500][500]",
                    }
                )
                if not np.isfinite(ds.unpack("wind_speed", probe["wind_speed"])).all():
                    log("source.incomplete", source=self.name, run=run_id, reason="last step fill")
                    continue
                return self._run(run_id, url, probe["time"])
            except HttpError as exc:
                log(
                    "source.candidate_error",
                    level="warning",
                    source=self.name,
                    run=run_id,
                    error=str(exc),
                )
                continue
        return None

    def _run(self, run_id: str, url: str, times: np.ndarray | None) -> Run:
        from datetime import UTC, datetime, timedelta

        ref = datetime.strptime(run_id, "%Y%m%dT%HZ").replace(tzinfo=UTC)
        valid = (
            epoch_seconds_to_dt(times)
            if times is not None
            else [ref + timedelta(hours=h) for h in range(EXPECTED_STEPS)]
        )
        assert run_id_of(ref) == run_id
        return Run(self.name, run_id, ref, url, valid)

    # -- fetching -------------------------------------------------------------------------
    def grid(self, ds: DapDataset) -> RegularGrid:
        axes = ds.fetch({"x": "", "y": ""})
        x0, dx = regular_axis(axes["x"], "x")
        y0, dy = regular_axis(axes["y"], "y")
        crs = cf_crs(ds.attributes["projection_lambert"])
        return RegularGrid(crs.to_wkt(), x0, dx, len(axes["x"]), y0, dy, len(axes["y"]), 2500.0)

    def fetch(self, http: HttpClient, run: Run, area: BBox) -> Subset:
        ds = DapDataset(http, run.url, cache=self.cache)
        full = self.grid(ds)
        j0, j1, i0, i1 = index_window(full, area)
        grid = full.subset(j0, j1, i0, i1)
        times_raw = ds.fetch({"time": ""})["time"]
        times = epoch_seconds_to_dt(times_raw)
        X, Y = np.meshgrid(grid.x(), grid.y())
        alpha = grid_north_angle(grid.crs, X, Y).astype(np.float32)
        height_dim = ds.variables["x_wind_10m"].shape
        if len(height_dim) != 4:
            raise ValueError(f"unexpected x_wind_10m rank: {height_dim}")
        bands = plan_bands(grid, area)
        chunk = min(len(times), steps_per_request(bands))
        notes = {
            "index_window": [j0, j1, i0, i1],
            "steps_per_request": chunk,
            **band_stats(grid, bands),
        }

        def steps() -> Iterator[tuple[int, Fields]]:
            for t0 in range(0, len(times), chunk):
                t1 = min(len(times), t0 + chunk) - 1
                arrays: dict[str, np.ndarray] = {}
                for var in ("x_wind_10m", "y_wind_10m", "wind_speed_of_gust"):
                    arr = np.full((t1 - t0 + 1, grid.ny, grid.nx), np.nan, dtype=np.float32)
                    for b in bands:
                        slab = (
                            f"[{t0}:{t1}][0][{j0 + b.r0}:{j0 + b.r1 - 1}]"
                            f"[{i0 + b.c0}:{i0 + b.c1 - 1}]"
                        )
                        raw = ds.fetch({var: slab})[var]
                        arr[:, b.r0 : b.r1, b.c0 : b.c1] = ds.unpack(var, raw)[:, 0]
                    arrays[var] = arr
                for k in range(t1 - t0 + 1):
                    u, v = rotate_grid_to_earth(
                        arrays["x_wind_10m"][k], arrays["y_wind_10m"][k], alpha
                    )
                    yield (
                        t0 + k,
                        {
                            "wind_u": u.astype(np.float32),
                            "wind_v": v.astype(np.float32),
                            "wind_gust": arrays["wind_speed_of_gust"][k].astype(np.float32),
                        },
                    )

        return Subset(grid, times, steps(), notes)


def lcc_convergence_deg(lon: float, lat_1: float = 63.3, lon_0: float = 15.0) -> float:
    """Analytic meridian convergence of the MEPS grid (used in tests/diagnostics)."""
    return math.sin(math.radians(lat_1)) * (lon - lon_0)
