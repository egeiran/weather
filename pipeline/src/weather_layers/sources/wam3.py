"""MyWaveWAM 3 km (MET Norway, pan-Arctic): waves and swell for days ~2-10.

Facts (verified live 2026-11-27, see docs/data-sources.md and decision 0012):
- Catalog https://thredds.met.no/thredds/catalog/fou-hi/mywavewam3_latest/catalog.xml, files
  MyWave_wam3_WAVE_<YYYYMMDD>T<HH>Z.nc (last 3 days kept).
- 18Z runs have 253 hourly steps, frt-18 h .. frt+234 h (ready ~6.5 h after nominal time);
  06Z runs only reach +114 h. We use the newest long run.
- Rotated lat/lon (pole lon 140, lat 25), 0.03 deg (~3 km), 1995 x 2379.
- hs, tp, thq (towards), hs_swell, tp_swell, thq_swell (towards); land = -9999999 (_FillValue);
  forecast_reference_time in DAYS since 1970. This is what api.met.no uses after +66 h.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import numpy as np

from ..dap import DapDataset
from ..grids import RegularGrid
from ..http import HttpClient, HttpError
from ..log import log
from ..mercator import BBox
from .base import Fields, Run, Source, Subset
from .projected import (
    band_stats,
    cf_crs,
    epoch_seconds_to_dt,
    index_window,
    plan_bands,
    regular_axis,
    steps_per_request,
)

CATALOG = "https://thredds.met.no/thredds/catalog/fou-hi/mywavewam3_latest/catalog.xml"
DODS_BASE = "https://thredds.met.no/thredds/dodsC/fou-hi/mywavewam3_latest/"
NAME_RE = re.compile(r"\bMyWave_wam3_WAVE_(\d{8})T(\d{2})Z\.nc\b")
MIN_STEPS = 240  # long runs only (18Z: 253 steps)


def enabled() -> bool:
    return os.environ.get("WEATHER_LAYERS_WAM3", "1") not in ("0", "false", "no", "off")


def min_lead_h() -> int:
    # WW3 (+800 m) covers the first 66 h; 48 h leaves margin for a stale WW3 run.
    return int(os.environ.get("WEATHER_LAYERS_WAM3_MIN_LEAD", "48"))


def step_h() -> int:
    # 3-hourly is plenty for days 2-10 and keeps the download to a third.
    return max(1, int(os.environ.get("WEATHER_LAYERS_WAM3_STEP_H", "3")))


VARS = {
    "hs": "wave_height",
    "tp": "wave_period",
    "thq": "wave_from_direction",
    "hs_swell": "swell_height",
    "tp_swell": "swell_period",
    "thq_swell": "swell_from_direction",
}
TOWARDS = {"thq", "thq_swell"}


class Wam3(Source):
    name = "wam3"
    label = "WAM3"
    model_name = "MyWaveWAM 3 km (MET Norway)"
    attribution = "MET Norway"
    license = "CC BY 4.0 / NLOD"
    products = ("waves", "swell")
    nominal_resolution_m = 3000.0

    def __init__(self, cache: bool = True) -> None:
        self.cache = cache

    def latest_complete_run(self, http: HttpClient, is_built=None) -> Run | None:
        xml = http.get(CATALOG).text
        names = sorted({m.group(0) for m in NAME_RE.finditer(xml)}, reverse=True)
        for name in names[:6]:
            m = NAME_RE.match(name)
            assert m
            run_id = f"{m.group(1)}T{m.group(2)}Z"
            url = DODS_BASE + name
            try:
                ds = DapDataset(http, url, cache=False)
                n = ds.variables["time"].shape[0]
                if n < MIN_STEPS:
                    continue  # short (06Z) run
                if is_built is not None and is_built(run_id):
                    return self._run(ds, run_id, url, None)
                _, ny, nx = ds.variables["hs"].shape
                sy, sx = max(1, ny // 10), max(1, nx // 10)
                probe = ds.fetch(
                    {
                        "forecast_reference_time": "",
                        "time": "",
                        "hs": f"[{n - 1}][0:{sy}:{ny - 1}][0:{sx}:{nx - 1}]",
                    }
                )
            except HttpError as exc:
                log(
                    "source.candidate_error",
                    level="warning",
                    source=self.name,
                    run=run_id,
                    error=str(exc),
                )
                continue
            if not np.isfinite(ds.unpack("hs", probe["hs"])).any():
                log("source.incomplete", source=self.name, run=run_id, reason="last step empty")
                continue
            return self._run(ds, run_id, url, probe)
        return None

    def _run(self, ds: DapDataset, run_id: str, url: str, probe: dict | None) -> Run:
        if probe is None:
            probe = ds.fetch({"forecast_reference_time": "", "time": ""})
        frt = datetime(1970, 1, 1, tzinfo=UTC) + timedelta(
            days=float(probe["forecast_reference_time"])
        )
        times = epoch_seconds_to_dt(probe["time"])
        lead0 = frt + timedelta(hours=min_lead_h())
        picked = [(i, t) for i, t in enumerate(times) if t >= lead0 and t.hour % step_h() == 0]
        return Run(
            self.name,
            run_id,
            frt,
            url,
            [t for _, t in picked],
            extra={"indices": [i for i, _ in picked]},
        )

    def fetch(self, http: HttpClient, run: Run, area: BBox) -> Subset:
        ds = DapDataset(http, run.url, cache=self.cache)
        if not run.extra.get("indices"):
            run = self._run(ds, run.run_id, run.url, None)
        idx: list[int] = run.extra["indices"]
        axes = ds.fetch({"rlon": "", "rlat": ""})
        x0, dx = regular_axis(axes["rlon"], "rlon")
        y0, dy = regular_axis(axes["rlat"], "rlat")
        crs = cf_crs(ds.attributes["projection_ob_tran"])
        full = RegularGrid(
            crs.to_wkt(),
            x0,
            dx,
            len(axes["rlon"]),
            y0,
            dy,
            len(axes["rlat"]),
            self.nominal_resolution_m,
        )
        j0, j1, i0, i1 = index_window(full, area)
        grid = full.subset(j0, j1, i0, i1)
        bands = plan_bands(grid, area)
        times = run.valid_times
        stride = idx[1] - idx[0] if len(idx) > 1 else 1
        if any(b - a != stride for a, b in zip(idx, idx[1:], strict=False)):
            raise RuntimeError("WAM3 time indices are not evenly spaced")
        chunk = min(len(times), steps_per_request(bands))
        notes = {
            "index_window": [j0, j1, i0, i1],
            "time_stride_h": stride,
            "steps_per_request": chunk,
            **band_stats(grid, bands),
        }

        def steps() -> Iterator[tuple[int, Fields]]:
            for a in range(0, len(times), chunk):
                b_ = min(len(times), a + chunk) - 1
                tsl = f"[{idx[a]}:{stride}:{idx[b_]}]"
                got = {}
                for var, field in VARS.items():
                    arr = np.full((b_ - a + 1, grid.ny, grid.nx), np.nan, dtype=np.float32)
                    for band in bands:
                        sl = (
                            f"{tsl}[{j0 + band.r0}:{j0 + band.r1 - 1}]"
                            f"[{i0 + band.c0}:{i0 + band.c1 - 1}]"
                        )
                        arr[:, band.r0 : band.r1, band.c0 : band.c1] = ds.unpack(
                            var, ds.fetch({var: sl})[var]
                        )
                    if var in TOWARDS:  # MyWaveWAM directions are "towards"
                        arr = np.mod(arr + 180.0, 360.0)
                    got[field] = arr
                for k in range(b_ - a + 1):
                    yield a + k, {f: arr[k] for f, arr in got.items()}

        return Subset(grid, times, steps(), notes)
