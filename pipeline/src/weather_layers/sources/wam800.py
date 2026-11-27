"""MyWaveWAM 800 m (MET Norway): coastal wave overlays for fjords and sounds.

Facts (verified live 2026-11-27, see docs/data-sources.md):
- Five coastal domains, each its own rotated lat/lon grid at 0.008 deg (~0.9 km):
  f/c0 Finnmark, n/c1 NordNorge, m/c2 MidtNorge, v/c3 Vestlandet, s/c4 Skagerrak.
- Files are a ring buffer, one per cycle hour (00/06/12/18), overwritten daily:
  .../dodsC/fou-hi/mywavewam800{X}_curr/MyWave_wam800_curr_c{N}WAVE{HH}.nc; ~4-4.5 h lag.
- 73 hourly steps frt-6..frt+66 h; time in seconds, forecast_reference_time in DAYS since 1970.
- hs (m), tp (s), thq: mean direction TOWARDS (we convert to "from"). Land = -9999999 (_FillValue).
- Covers about a quarter of the coastal sea but reaches into fjords WW3 4 km cannot resolve.

Used as an overlay on WW3: where an 800 m grid has data, it replaces WW3 for total waves.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from ..dap import DapDataset
from ..grids import RegularGrid
from ..http import HttpClient, HttpError
from ..log import log
from ..mercator import BBox
from .base import Fields
from .projected import (
    cf_crs,
    epoch_seconds_to_dt,
    footprint_bbox,
    index_window,
    plan_bands,
    regular_axis,
)

URL = "https://thredds.met.no/thredds/dodsC/fou-hi/mywavewam800{x}_curr/MyWave_wam800_curr_c{n}WAVE{hh}.nc"
DOMAINS = {"f": 0, "n": 1, "m": 2, "v": 3, "s": 4}
NAMES = {"f": "Finnmark", "n": "NordNorge", "m": "MidtNorge", "v": "Vestlandet", "s": "Skagerrak"}
RESOLUTION_M = 890.0
CHUNK_STEPS = 12


def enabled() -> bool:
    return os.environ.get("WEATHER_LAYERS_WAM800", "1") not in ("0", "false", "no", "off")


def run_hours() -> list[str]:
    env = os.environ.get("WEATHER_LAYERS_WAM800_RUN_HOURS", "00,06,12,18")
    return [f"{int(h):02d}" for h in env.split(",") if h.strip()]


@dataclass
class Overlay:
    """One 800 m domain, cut to the area, delivering fields for the base run's valid times."""

    name: str
    run: str
    grid: RegularGrid
    footprint: BBox
    products: tuple[str, ...]
    _ds: DapDataset
    _window: tuple[int, int, int, int]
    _bands: list
    _index: dict[datetime, int]  # valid time -> index in the overlay file
    _cache: dict[int, Fields] = field(default_factory=dict)

    def covers(self, t: datetime) -> bool:
        return t in self._index

    def fields(self, times: list[datetime], t_index: int) -> Fields | None:
        """Fields at base time index `t_index` (None if this run has no such time)."""
        t = times[t_index]
        if t not in self._index:
            return None
        if t_index not in self._cache:
            self._load(times, t_index)
        return self._cache.get(t_index)

    def _load(self, times: list[datetime], t_index: int) -> None:
        """Load a block of consecutive base times in one request per variable and strip."""
        self._cache.clear()
        block = [
            i
            for i in range(t_index, min(len(times), t_index + CHUNK_STEPS))
            if times[i] in self._index
        ]
        idx = [self._index[times[i]] for i in block]
        # keep only the contiguous run of overlay indices starting at the first
        cont = [block[0]]
        for b, prev_i, cur_i in zip(block[1:], idx[:-1], idx[1:], strict=False):
            if cur_i != prev_i + 1:
                break
            cont.append(b)
        a, b_ = self._index[times[cont[0]]], self._index[times[cont[-1]]]
        j0, _j1, i0, _i1 = self._window
        got: dict[str, np.ndarray] = {}
        for var in ("hs", "tp", "thq"):
            arr = np.full((b_ - a + 1, self.grid.ny, self.grid.nx), np.nan, dtype=np.float32)
            for band in self._bands:
                sl = (
                    f"[{a}:{b_}][{j0 + band.r0}:{j0 + band.r1 - 1}]"
                    f"[{i0 + band.c0}:{i0 + band.c1 - 1}]"
                )
                raw = self._ds.fetch({var: sl})[var]
                arr[:, band.r0 : band.r1, band.c0 : band.c1] = self._ds.unpack(var, raw)
            got[var] = arr
        for k, ti in enumerate(cont):
            hs = got["hs"][k]
            self._cache[ti] = {
                "wave_height": hs,
                "wave_period": got["tp"][k],
                # MyWaveWAM directions are "towards"; the waves product expects "from".
                "wave_from_direction": np.mod(got["thq"][k] + 180.0, 360.0),
            }


def build_overlays(
    http: HttpClient, area: BBox, base_times: list[datetime], cache: bool = True
) -> list[Overlay]:
    """Newest complete run per domain that intersects the area (overlays for WW3)."""
    if not enabled():
        return []
    overlays: list[Overlay] = []
    wanted = set(base_times)
    for x, n in DOMAINS.items():
        best: tuple[float, str] | None = None
        for hh in run_hours():
            url = URL.format(x=x, n=n, hh=hh)
            try:
                probe = DapDataset(http, url, cache=False).fetch({"forecast_reference_time": ""})
            except HttpError as exc:
                log("overlay.skip", level="warning", domain=NAMES[x], hh=hh, error=str(exc))
                continue
            frt_days = float(probe["forecast_reference_time"])
            if best is None or frt_days > best[0]:
                best = (frt_days, url)
        if best is None:
            continue
        frt = epoch_seconds_to_dt(np.array([best[0] * 86400.0]))[0]
        run_id = frt.strftime("%Y%m%dT%HZ")
        # Content behind the URL changes daily (ring buffer): namespace the raw cache by run.
        ds = DapDataset(http.namespaced(f"wam800:{x}:{run_id}"), best[1], cache=cache)
        try:
            axes = ds.fetch({"rlon": "", "rlat": "", "time": ""})
            crs = cf_crs(ds.attributes["projection_3"])
        except (HttpError, KeyError) as exc:
            log("overlay.skip", level="warning", domain=NAMES[x], error=str(exc))
            continue
        x0, dx = regular_axis(axes["rlon"], "rlon")
        y0, dy = regular_axis(axes["rlat"], "rlat")
        full = RegularGrid(
            crs.to_wkt(), x0, dx, len(axes["rlon"]), y0, dy, len(axes["rlat"]), RESOLUTION_M
        )
        foot = footprint_bbox(full)
        if (
            foot.east <= area.west
            or foot.west >= area.east
            or foot.north <= area.south
            or foot.south >= area.north
        ):
            continue
        try:
            j0, j1, i0, i1 = index_window(full, area)
        except ValueError:
            continue
        grid = full.subset(j0, j1, i0, i1)
        bands = plan_bands(grid, area, n_bands=2)
        if not bands:
            continue
        times = epoch_seconds_to_dt(axes["time"])
        index = {t: i for i, t in enumerate(times) if t in wanted}
        if not index:
            continue
        overlays.append(
            Overlay(
                name=f"wam800-{NAMES[x]}",
                run=run_id,
                grid=grid,
                footprint=footprint_bbox(grid),
                products=("waves",),
                _ds=ds,
                _window=(j0, j1, i0, i1),
                _bands=bands,
                _index=index,
            )
        )
        log(
            "overlay.ready",
            name=f"wam800-{NAMES[x]}",
            run=run_id,
            cells=grid.nx * grid.ny,
            times=len(index),
        )
    return overlays


# 800 m data gets one zoom level more than WW3 (z6 ~ 1 km px at 65N), only where it exists.
OVERLAY_MAX_ZOOM = 6
