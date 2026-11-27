"""NorKyst v3 800 m (MET Norway): surface current and sea temperature.

Facts (verified live 2026-11-27, see docs/data-sources.md):
- The old NorKyst800 v2 aggregate (sea/norkyst800m/1h/aggregate_be) ended 2025-10; MET's
  current product is NorKyst v3: OPeNDAP .../dodsC/fou-hi/norkystv3_800m_m00_be ("best
  estimate" aggregate over all runs).
- One run per day at 00Z, +0..+120 h hourly (121 steps), complete ~06:40 UTC.
- Polar stereographic grid (WGS84 ellipsoid), X/Y in metres at exactly 800 m.
- u_eastward/v_northward are TRUE east/north (no grid-relative u/v in v3); "going to".
- Int16 packed (scale 0.001; temperature offset +10), _FillValue -32767 = land.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import numpy as np

from ..dap import DapDataset
from ..grids import RegularGrid
from ..http import HttpClient, HttpError
from ..log import log
from ..mercator import BBox
from .base import Fields, Run, Source, Subset, run_id_of
from .projected import cf_crs, epoch_seconds_to_dt, index_window, regular_axis

URL = "https://thredds.met.no/thredds/dodsC/fou-hi/norkystv3_800m_m00_be"
STEPS = 121
MAX_REQUEST_BYTES = 24 * 1024 * 1024


def _stride(cells: int) -> int:
    env = os.environ.get("WEATHER_LAYERS_NORKYST_STRIDE", "auto")
    if env != "auto":
        return max(1, int(env))
    # Full 800 m for small areas; 1.6 km for coast-sized windows (4x fewer bytes).
    return 1 if cells <= 1_000_000 else 2


class NorKyst(Source):
    name = "norkyst"
    label = "NorKyst"
    model_name = "NorKyst v3 800 m (MET Norway)"
    attribution = "MET Norway"
    license = "CC BY 4.0 / NLOD"
    products = ("current",)
    nominal_resolution_m = 800.0

    def __init__(self, cache: bool = True) -> None:
        self.cache = cache
        self._stride = 1

    def max_zoom(self) -> int:
        # 800 m -> z7 (517 m/px at 65N); with stride 2 (1.6 km) -> z6.
        return 7 if self._stride == 1 else 6

    def latest_complete_run(self, http: HttpClient, is_built=None) -> Run | None:
        try:
            ds = DapDataset(http, URL, cache=False)
            n = ds.variables["time"].shape[0]
            probe = ds.fetch({"forecast_reference_time": "", "time": f"[{n - STEPS}:{n - 1}]"})
        except HttpError as exc:
            log("source.discover_error", level="warning", source=self.name, error=str(exc))
            return None
        frt = float(probe["forecast_reference_time"])
        times = np.asarray(probe["time"], dtype=np.float64)
        ok = (
            abs(times[0] - frt) < 1
            and abs(times[-1] - (frt + 120 * 3600)) < 1
            and np.allclose(np.diff(times), 3600)
        )
        ref = epoch_seconds_to_dt(np.array([frt]))[0]
        run_id = run_id_of(ref)
        if not ok:
            # The newest run is still being appended: the previous run is not addressable in
            # the best-estimate aggregate any more, so report "no new complete run".
            log("source.incomplete", source=self.name, run=run_id, n=n)
            return None
        return Run(
            self.name, run_id, ref, URL, epoch_seconds_to_dt(times), extra={"t0": n - STEPS, "n": n}
        )

    def fetch(self, http: HttpClient, run: Run, area: BBox) -> Subset:
        h = http.namespaced(f"norkyst:{run.run_id}:{run.extra['t0']}")
        ds = DapDataset(h, URL, cache=self.cache)
        axes = ds.fetch({"X": "", "Y": ""})
        x0, dx = regular_axis(axes["X"], "X")
        y0, dy = regular_axis(axes["Y"], "Y")
        crs = cf_crs(ds.attributes["projection_stere"])
        full = RegularGrid(crs.to_wkt(), x0, dx, len(axes["X"]), y0, dy, len(axes["Y"]), 800.0)
        j0, j1, i0, i1 = index_window(full, area)
        s = _stride((j1 - j0) * (i1 - i0))
        self._stride = s
        j1 = j0 + ((j1 - j0 - 1) // s) * s + 1
        i1 = i0 + ((i1 - i0 - 1) // s) * s + 1
        grid = RegularGrid(
            full.crs_wkt,
            x0 + i0 * dx,
            dx * s,
            (i1 - i0 - 1) // s + 1,
            y0 + j0 * dy,
            dy * s,
            (j1 - j0 - 1) // s + 1,
            800.0 * s,
        )
        t0 = run.extra["t0"]
        times = run.valid_times
        step_bytes = grid.nx * grid.ny * 4
        chunk = max(1, min(len(times), MAX_REQUEST_BYTES // step_bytes))
        notes = {
            "index_window": [j0, j1, i0, i1],
            "stride": s,
            "steps_per_request": chunk,
            "aggregate_time_index0": t0,
        }

        def steps() -> Iterator[tuple[int, Fields]]:
            for a in range(0, len(times), chunk):
                b = min(len(times), a + chunk) - 1
                sl = f"[{t0 + a}:{t0 + b}][0][{j0}:{s}:{j1 - 1}][{i0}:{s}:{i1 - 1}]"
                got = {}
                for var in ("u_eastward", "v_northward", "temperature"):
                    res = ds.fetch({var: sl, "time": f"[{t0 + a}:{t0 + b}]"})
                    check = epoch_seconds_to_dt(res["time"])
                    if check != times[a : b + 1]:
                        raise RuntimeError("NorKyst aggregate changed during fetch")
                    got[var] = ds.unpack(var, res[var])[:, 0]
                for k in range(b - a + 1):
                    yield (
                        a + k,
                        {
                            "current_u": got["u_eastward"][k],
                            "current_v": got["v_northward"][k],
                            "sea_temperature": got["temperature"][k],
                        },
                    )

        return Subset(grid, times, steps(), notes)
