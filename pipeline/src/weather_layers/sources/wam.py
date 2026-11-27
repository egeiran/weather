"""Regional waves: MET Norway WAVEWATCH III 4 km (the successor of MyWaveWAM 4 km).

Facts (verified live 2026-11-27, see docs/data-sources.md and decision 0004):
- MyWaveWAM 4 km is no longer on THREDDS; MET's 4 km regional wave model is WW3 4 km.
- Catalog https://thredds.met.no/thredds/catalog/ww3_4km_latest_files/catalog.xml, files
  ww3_<YYYYMMDD>T<HH>Z.nc; runs 00/06/12/18Z, published ~3-3.5 h after nominal time.
- 73 hourly steps: frt-6 h .. frt+66 h (lead 0 at index 6).
- Rotated lat/lon grid (pole lon 140, lat 22), 0.04 deg (~4.4 km).
- hs, tp, dir (mean direction, FROM); partitions: 0 = wind sea, 1 = swell (phs1/ptp1/pdir1).
  Land and absent partitions are NaN; _FillValue -999.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

import numpy as np

from ..dap import DapDataset
from ..grids import RegularGrid
from ..http import HttpClient, HttpError
from ..log import log
from ..mercator import BBox
from .base import Fields, Run, Source, Subset, run_id_of
from .projected import cf_crs, epoch_seconds_to_dt, index_window, regular_axis

CATALOG = "https://thredds.met.no/thredds/catalog/ww3_4km_latest_files/catalog.xml"
DODS_BASE = "https://thredds.met.no/thredds/dodsC/ww3_4km_latest_files/"
NAME_RE = re.compile(r"\bww3_(\d{8})T(\d{2})Z\.nc\b")
N_TIMES = 73
LEAD0 = 6
MAX_REQUEST_BYTES = 24 * 1024 * 1024

VARS = {
    "hs": "wave_height",
    "tp": "wave_period",
    "dir": "wave_from_direction",
    "phs1": "swell_height",
    "ptp1": "swell_period",
    "pdir1": "swell_from_direction",
}


class Wam(Source):
    """Named after the slot in the spec ("WAM"); the model behind it is WW3 4 km."""

    name = "wam"
    label = "WW3"
    model_name = "WAVEWATCH III 4 km (MET Norway)"
    attribution = "MET Norway"
    license = "CC BY 4.0 / NLOD"
    products = ("waves", "swell")
    nominal_resolution_m = 4400.0

    def __init__(self, cache: bool = True) -> None:
        self.cache = cache

    def latest_complete_run(self, http: HttpClient, is_built=None) -> Run | None:
        xml = http.get(CATALOG).text
        names = sorted({m.group(0) for m in NAME_RE.finditer(xml)}, reverse=True)
        for name in names[:4]:
            m = NAME_RE.match(name)
            assert m
            run_id = f"{m.group(1)}T{m.group(2)}Z"
            url = DODS_BASE + name
            if is_built is not None and is_built(run_id):
                return Run(self.name, run_id, _ref(run_id), url, [])
            try:
                ds = DapDataset(http, url, cache=False)
                probe = ds.fetch(
                    {"forecast_reference_time": "", "time": "", "hs": f"[{N_TIMES - 1}][450][340]"}
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
            t = np.asarray(probe["time"], dtype=np.float64)
            frt = float(probe["forecast_reference_time"])
            if len(t) != N_TIMES or abs(t[-1] - (frt + 66 * 3600)) > 1:
                log("source.incomplete", source=self.name, run=run_id, steps=len(t))
                continue
            if not np.isfinite(ds.unpack("hs", probe["hs"])).all():
                log("source.incomplete", source=self.name, run=run_id, reason="last step NaN")
                continue
            ref = epoch_seconds_to_dt(np.array([frt]))[0]
            return Run(self.name, run_id_of(ref), ref, url, epoch_seconds_to_dt(t[LEAD0:]))
        return None

    def fetch(self, http: HttpClient, run: Run, area: BBox) -> Subset:
        ds = DapDataset(http, run.url, cache=self.cache)
        axes = ds.fetch({"rlon": "", "rlat": "", "time": ""})
        x0, dx = regular_axis(axes["rlon"], "rlon")
        y0, dy = regular_axis(axes["rlat"], "rlat")
        crs = cf_crs(ds.attributes["rotated_pole"])
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
        times = epoch_seconds_to_dt(axes["time"])[LEAD0:]
        step_bytes = grid.nx * grid.ny * 4
        chunk = max(1, min(len(times), MAX_REQUEST_BYTES // step_bytes))
        notes = {
            "index_window": [j0, j1, i0, i1],
            "steps_per_request": chunk,
            "model": "WW3 4 km; swell = partition 1, wind sea = partition 0",
        }

        def steps() -> Iterator[tuple[int, Fields]]:
            for a in range(0, len(times), chunk):
                b = min(len(times), a + chunk) - 1
                sl = f"[{LEAD0 + a}:{LEAD0 + b}][{j0}:{j1 - 1}][{i0}:{i1 - 1}]"
                got = {}
                for var, field in VARS.items():
                    got[field] = ds.unpack(var, ds.fetch({var: sl})[var])
                for k in range(b - a + 1):
                    yield a + k, {f: arr[k] for f, arr in got.items()}

        return Subset(grid, times, steps(), notes)


def _ref(run_id: str):
    from datetime import UTC, datetime

    return datetime.strptime(run_id, "%Y%m%dT%HZ").replace(tzinfo=UTC)
