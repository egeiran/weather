"""ECMWF IFS open data 0.25 deg (CC BY 4.0): wind, gusts and waves for days ~3-10.

Facts (verified live 2026-11-27, see docs/data-sources.md):
- Files: <base>/YYYYMMDD/HHz/ifs/0p25/{oper|wave}/YYYYMMDDHH0000-<step>h-{oper|wave}-fc.grib2
  with a JSON-lines .index (param, levtype, _offset, _length) -> byte-range download per field.
- 00z/12z runs: steps 0-144 every 3 h, then 150-360 every 6 h. 06z/18z stop at 144 h, so we
  use 00z/12z only. A run is uploaded in one batch (~07:34 / ~19:34 UTC); the last object is
  the wave index of the last step, which we use as the completeness marker.
- Gusts: `10fg` = max over the last 1 h (steps <= 90), `10fg3` = last 3 h (93-144),
  `10fg` = last 6 h (150+). We store whatever the step offers and record the window.
- Waves: swh, pp1d (peak period, like WW3 tp), mwd (FROM, degrees true). No swell/wind-sea
  partitions in open data. Wave land points are bitmap-masked.
- Grid: regular lat/lon, row 0 = 90N, first column = 180E (= -180), so lon -180..179.75.
- No server-side spatial subsetting: one global field (~0.4-0.7 MB) is the smallest unit.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import numpy as np
from pyproj import CRS

from ..grids import RegularGrid
from ..http import HttpClient, HttpError
from ..log import log
from ..mercator import BBox
from .base import Fields, Run, Source, Subset, run_id_of

DEFAULT_BASE = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
RES = 0.25
NI, NJ = 1440, 721
LAST_STEP = 360  # completeness marker step for 00z/12z


def base_url() -> str:
    return os.environ.get("WEATHER_LAYERS_ECMWF_BASE", DEFAULT_BASE).rstrip("/")


def min_step() -> int:
    # MEPS/WW3 cover the first ~2.5 days; ECMWF is only shown after them. 48 h leaves margin
    # for a stale regional run (see decision 0006).
    return int(os.environ.get("WEATHER_LAYERS_ECMWF_MIN_STEP", "48"))


def max_step() -> int:
    return int(os.environ.get("WEATHER_LAYERS_ECMWF_MAX_STEP", "240"))


def steps_00_12() -> list[int]:
    return list(range(0, 145, 3)) + list(range(150, LAST_STEP + 1, 6))


def file_url(ref: datetime, stream: str, step: int, ext: str) -> str:
    d = ref.strftime("%Y%m%d")
    hh = ref.strftime("%H")
    return f"{base_url()}/{d}/{hh}z/ifs/0p25/{stream}/{d}{hh}0000-{step}h-{stream}-fc.{ext}"


def parse_index(text: str) -> dict[str, dict]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("levtype") not in (None, "sfc"):
            continue
        out[rec["param"]] = rec
    return out


def decode_grib(data: bytes) -> np.ndarray:
    import eccodes

    h = eccodes.codes_new_from_message(data)
    try:
        ni, nj = eccodes.codes_get(h, "Ni"), eccodes.codes_get(h, "Nj")
        lat0 = eccodes.codes_get(h, "latitudeOfFirstGridPointInDegrees")
        lon0 = eccodes.codes_get(h, "longitudeOfFirstGridPointInDegrees")
        d = eccodes.codes_get(h, "iDirectionIncrementInDegrees")
        if (ni, nj) != (NI, NJ) or abs(lat0 - 90) > 1e-6 or abs(d - RES) > 1e-9:
            raise ValueError(f"unexpected ECMWF grid {ni}x{nj} lat0={lat0} d={d}")
        if abs((lon0 % 360) - 180) > 1e-6:
            raise ValueError(f"unexpected first longitude {lon0}")
        vals = eccodes.codes_get_values(h).reshape(nj, ni).astype(np.float32)
        if eccodes.codes_get(h, "bitmapPresent"):
            bitmap = eccodes.codes_get_array(h, "bitmap").reshape(nj, ni)
            vals[bitmap == 0] = np.nan
    finally:
        eccodes.codes_release(h)
    return vals


class Ecmwf(Source):
    name = "ecmwf"
    label = "ECMWF"
    model_name = "ECMWF IFS open data 0.25°"
    attribution = "ECMWF"
    license = "CC BY 4.0"
    products = ("wind", "waves")
    nominal_resolution_m = 14000.0

    def __init__(self, cache: bool = True) -> None:
        self.cache = cache

    def min_zoom(self) -> int:
        return 0

    def latest_complete_run(self, http: HttpClient, is_built=None) -> Run | None:
        now = datetime.now(UTC)
        start = now.replace(hour=12 if now.hour >= 12 else 0, minute=0, second=0, microsecond=0)
        for k in range(6):
            ref = start - timedelta(hours=12 * k)
            run_id = run_id_of(ref)
            if is_built is not None and is_built(run_id):
                return self._run(ref)
            url = file_url(ref, "wave", LAST_STEP, "index")
            try:
                r = http.get(url, allow_status=(200, 403, 404))
            except HttpError as exc:
                log(
                    "source.candidate_error",
                    level="warning",
                    source=self.name,
                    run=run_id,
                    error=str(exc),
                )
                continue
            if r.status == 200 and r.content.strip():
                return self._run(ref)
            log("source.incomplete", source=self.name, run=run_id, status=r.status)
        return None

    def _run(self, ref: datetime) -> Run:
        steps = [s for s in steps_00_12() if min_step() <= s <= max_step()]
        return Run(
            self.name,
            run_id_of(ref),
            ref,
            base_url(),
            [ref + timedelta(hours=s) for s in steps],
            extra={"steps": steps},
        )

    def fetch(self, http: HttpClient, run: Run, area: BBox) -> Subset:
        margin = 2
        r0 = max(0, math.floor((90 - area.north) / RES) - margin)
        r1 = min(NJ, math.ceil((90 - area.south) / RES) + 1 + margin)
        c0 = max(0, math.floor((area.west + 180) / RES) - margin)
        c1 = min(NI, math.ceil((area.east + 180) / RES) + 1 + margin)
        grid = RegularGrid(
            CRS.from_epsg(4326).to_wkt(),
            -180 + c0 * RES,
            RES,
            c1 - c0,
            90 - r0 * RES,
            -RES,
            r1 - r0,
            self.nominal_resolution_m,
        )
        steps = run.extra.get("steps") or self._run(run.reference_time).extra["steps"]
        times = [run.reference_time + timedelta(hours=s) for s in steps]
        gust_windows: dict[str, int] = {}
        notes = {
            "crop_rows": [r0, r1],
            "crop_cols": [c0, c1],
            "steps": steps,
            "gust_window_hours": gust_windows,
        }

        def get_field(ref, stream, step, rec) -> np.ndarray:
            url = file_url(ref, stream, step, "grib2")
            a, n = int(rec["_offset"]), int(rec["_length"])
            data = http.get(
                url,
                headers={"Range": f"bytes={a}-{a + n - 1}"},
                cache=self.cache,
                allow_status=(200, 206),
            ).content
            if len(data) != n:
                raise RuntimeError(f"short range read for {url}: {len(data)} != {n}")
            return decode_grib(data)[r0:r1, c0:c1]

        def one_step(step: int) -> Fields:
            ref = run.reference_time
            oper = parse_index(
                http.get(file_url(ref, "oper", step, "index"), cache=self.cache).text
            )
            wave = parse_index(
                http.get(file_url(ref, "wave", step, "index"), cache=self.cache).text
            )
            gust_param = "10fg3" if "10fg3" in oper else "10fg"
            window = 3 if gust_param == "10fg3" else (1 if step <= 90 else 6)
            gust_windows[str(step)] = window
            jobs = {
                "wind_u": ("oper", oper["10u"]),
                "wind_v": ("oper", oper["10v"]),
                "wind_gust": ("oper", oper[gust_param]),
                "wave_height": ("wave", wave["swh"]),
                "wave_period": ("wave", wave["pp1d"]),
                "wave_from_direction": ("wave", wave["mwd"]),
            }
            with ThreadPoolExecutor(max_workers=4) as pool:
                futs = {
                    k: pool.submit(get_field, ref, s, step, rec) for k, (s, rec) in jobs.items()
                }
                return {k: f.result() for k, f in futs.items()}

        def iterate() -> Iterator[tuple[int, Fields]]:
            with ThreadPoolExecutor(max_workers=2) as ahead:
                nxt = ahead.submit(one_step, steps[0]) if steps else None
                for i in range(len(steps)):
                    assert nxt is not None
                    fields = nxt.result()
                    if i + 1 < len(steps):
                        nxt = ahead.submit(one_step, steps[i + 1])
                    yield i, fields

        return Subset(grid, times, iterate(), notes)
