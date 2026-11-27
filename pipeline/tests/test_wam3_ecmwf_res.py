"""MyWaveWAM 3 km source, ECMWF resolution/wave settings and the resulting stitching."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise

import numpy as np
import pytest
from pyproj import CRS, Transformer

from weather_layers.mercator import BBox
from weather_layers.sources import ecmwf, wam3
from weather_layers.sources.base import iso
from weather_layers.stitch import stitch

from .fakes import t

ROT = {
    "grid_mapping_name": "rotated_latitude_longitude",
    "grid_north_pole_longitude": 140.0,
    "grid_north_pole_latitude": 25.0,
    "earth_radius": 6371000.0,
}
FILL = -9999999.0
AREA = BBox(7.5, 63.2, 10.0, 64.2)
FRT = t(26, 18)
EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
N_LONG, N_SHORT = 253, 133


@dataclass
class _Decl:
    shape: tuple[int, ...]


def _axes():
    """Small rotated grid (0.03 deg) around the dev area, in the real model's frame."""
    tr = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_cf(ROT), always_xy=True)
    x, y = tr.transform(
        [AREA.west, AREA.east, AREA.west, AREA.east],
        [AREA.south, AREA.south, AREA.north, AREA.north],
    )
    rlon = np.round(np.arange(min(x) - 0.3, max(x) + 0.3, 0.03), 6)
    rlat = np.round(np.arange(min(y) - 0.3, max(y) + 0.3, 0.03), 6)
    return rlon.astype(np.float32), rlat.astype(np.float32)


class FakeDs:
    """Stands in for DapDataset: serves synthetic hyperslabs like THREDDS would."""

    files: dict[str, int] = {}

    def __init__(self, http, url, cache=True):
        self.n = self.files[url.rsplit("/", 1)[-1]]
        self.rlon, self.rlat = _axes()
        ny, nx = len(self.rlat), len(self.rlon)
        land = np.zeros((ny, nx), bool)
        land[: ny // 3, : nx // 3] = True
        shape = (self.n, ny, nx)
        self.data = {
            "hs": np.full(shape, 2.0, np.float32),
            "tp": np.full(shape, 9.0, np.float32),
            "thq": np.full(shape, 90.0, np.float32),  # towards east -> from west (270)
            "hs_swell": np.full(shape, 1.0, np.float32),
            "tp_swell": np.full(shape, 12.0, np.float32),
            "thq_swell": np.full(shape, 350.0, np.float32),  # towards ~N -> from 170
        }
        for arr in self.data.values():
            arr[:, land] = FILL
        self.variables = {"time": _Decl((self.n,)), "hs": _Decl(shape)}
        self.attributes = {"projection_ob_tran": ROT} | {v: {"_FillValue": FILL} for v in self.data}
        self.requests: list[dict] = []

    def fetch(self, query: dict[str, str]) -> dict[str, np.ndarray]:
        self.requests.append(query)
        out = {}
        for name, sl in query.items():
            if name == "forecast_reference_time":
                out[name] = np.array((FRT - EPOCH).total_seconds() / 86400.0)
            elif name == "time":
                start = (FRT - timedelta(hours=18)).timestamp()
                out[name] = start + 3600.0 * np.arange(self.n)
            elif name in ("rlon", "rlat"):
                out[name] = getattr(self, name)
            else:
                idx = []
                for part in re.findall(r"\[([^\]]+)\]", sl):
                    nums = [int(v) for v in part.split(":")]
                    if len(nums) == 1:
                        idx.append(slice(nums[0], nums[0] + 1))
                    elif len(nums) == 2:
                        idx.append(slice(nums[0], nums[1] + 1))
                    else:
                        idx.append(slice(nums[0], nums[2] + 1, nums[1]))
                out[name] = self.data[name][tuple(idx)]
        return out

    def unpack(self, name, raw):
        data = raw.astype(np.float32)
        data[np.isclose(raw, FILL)] = np.nan
        return data


class FakeHttp:
    def __init__(self, names):
        self.catalog = "".join(f'<dataset name="{n}" urlPath="x/{n}"/>' for n in names)

    def get(self, url, cache=True):
        assert url == wam3.CATALOG
        return type("R", (), {"text": self.catalog})()


@pytest.fixture
def fake_wam3(monkeypatch):
    FakeDs.files = {
        "MyWave_wam3_WAVE_20261127T06Z.nc": N_SHORT,  # newest, but only +114 h
        "MyWave_wam3_WAVE_20261126T18Z.nc": N_LONG,
    }
    monkeypatch.setattr(wam3, "DapDataset", FakeDs)
    return FakeHttp(list(FakeDs.files))


def test_wam3_picks_long_run_three_hourly_after_lead(fake_wam3, monkeypatch):
    monkeypatch.delenv("WEATHER_LAYERS_WAM3_MIN_LEAD", raising=False)
    monkeypatch.delenv("WEATHER_LAYERS_WAM3_STEP_H", raising=False)
    run = wam3.Wam3(cache=False).latest_complete_run(fake_wam3)
    assert run is not None and run.run_id == "20261126T18Z"  # 06Z skipped: too short
    assert run.reference_time == FRT
    assert run.valid_times[0] == FRT + timedelta(hours=48)
    assert all(b - a == timedelta(hours=3) for a, b in pairwise(run.valid_times))
    assert run.valid_times[-1] <= FRT + timedelta(hours=234)


def test_wam3_fetch_directions_from_and_land_nan(fake_wam3):
    src = wam3.Wam3(cache=False)
    run = src.latest_complete_run(fake_wam3)
    sub = src.fetch(fake_wam3, run, AREA)
    seen = 0
    for _k, fields in sub.steps:
        assert set(fields) == set(wam3.VARS.values())
        sea = np.isfinite(fields["wave_height"])
        assert sea.any() and (~sea).any()  # land stays no-data
        np.testing.assert_allclose(fields["wave_from_direction"][sea], 270.0)
        np.testing.assert_allclose(fields["swell_from_direction"][sea], 170.0)
        np.testing.assert_allclose(fields["swell_period"][sea], 12.0)
        seen += 1
    assert seen == len(sub.times) == len(run.valid_times)


def test_ecmwf_resolution_file_names_and_waves(monkeypatch):
    ref = t(27, 0)
    monkeypatch.setenv("WEATHER_LAYERS_ECMWF_RESOLUTION", "0p1")
    assert ecmwf.file_url(ref, "oper", 48, "index").endswith(
        "/20261127/00z/ifs/0p1/oper/20261127000000-48h-oper-fc-sfc.index"
    )
    monkeypatch.setenv("WEATHER_LAYERS_ECMWF_RESOLUTION", "0p25")
    assert ecmwf.file_url(ref, "wave", 360, "index").endswith(
        "/ifs/0p25/wave/20261127000000-360h-wave-fc.index"
    )
    monkeypatch.setenv("WEATHER_LAYERS_ECMWF_RESOLUTION", "1p0")
    with pytest.raises(ValueError):
        ecmwf.resolution()
    monkeypatch.setenv("WEATHER_LAYERS_ECMWF_RESOLUTION", "0p1")
    # waves only as a fallback when MyWaveWAM 3 km is switched off
    monkeypatch.delenv("WEATHER_LAYERS_ECMWF_WAVES", raising=False)
    monkeypatch.delenv("WEATHER_LAYERS_WAM3", raising=False)
    src = ecmwf.Ecmwf(cache=False)
    assert src.products == ("wind",) and src.res == 0.1 and "0.1" in src.model_name
    monkeypatch.setenv("WEATHER_LAYERS_WAM3", "0")
    assert ecmwf.Ecmwf(cache=False).products == ("wind", "waves")
    monkeypatch.setenv("WEATHER_LAYERS_ECMWF_WAVES", "0")
    assert ecmwf.Ecmwf(cache=False).products == ("wind",)


def _meta(run_id, times, products):
    return {
        "run_id": run_id,
        "times": [iso(x) for x in times],
        "products": {p: {} for p in products},
    }


def test_waves_stitch_ww3_then_wam3_then_ecmwf():
    ww3_t = [t(27, 0) + timedelta(hours=h) for h in range(67)]
    w3_t = [FRT + timedelta(hours=h) for h in range(48, 235, 3)]
    ec_t = [t(27, 0) + timedelta(hours=h) for h in [*range(48, 145, 3), *range(150, 241, 6)]]
    runs = {
        "wam": _meta("20261127T00Z", ww3_t, ["waves", "swell"]),
        "wam3": _meta("20261126T18Z", w3_t, ["waves", "swell"]),
        "ecmwf": _meta("20261127T00Z", ec_t, ["wind", "waves"]),
    }
    for product in ("waves", "swell"):
        segs = stitch(product, runs)
        assert [s.source for s in segs][:2] == ["wam", "wam3"]
        assert segs[1].times[0] > ww3_t[-1]
        assert segs[1].times[-1] == w3_t[-1]
    # ECMWF only adds waves after MyWaveWAM ends (+240 h vs +234 h)
    segs = stitch("waves", runs)
    assert segs[-1].source == "ecmwf" and segs[-1].times[0] > w3_t[-1]
    # without wam3 (switched off), ECMWF fills in after WW3 as before
    del runs["wam3"]
    assert [s.source for s in stitch("waves", runs)][:2] == ["wam", "ecmwf"]
