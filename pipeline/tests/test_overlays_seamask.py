"""Overlays (higher-resolution grids replacing the base where they have data) and clipping a
coarse ocean model to a reference coastline."""

from dataclasses import dataclass
from datetime import timedelta

import numpy as np

from weather_layers import mercator
from weather_layers.build import SeaMask, build_run
from weather_layers.encoding import read_png
from weather_layers.grids import RegularGrid
from weather_layers.mercator import BBox
from weather_layers.sources.base import Run, Source, Subset
from weather_layers.sources.projected import footprint_bbox
from weather_layers.storage import LocalStorage

from .fakes import LCC, t

AREA = BBox(7.5, 63.2, 10.0, 64.2)


def _waves(grid: RegularGrid, hs: float, land_cols: slice | None = None):
    h = np.full((grid.ny, grid.nx), hs, dtype=np.float32)
    if land_cols is not None:
        h[:, land_cols] = np.nan
    return {"wave_height": h, "wave_period": h * 0 + 8, "wave_from_direction": h * 0 + 270}


class WaveSource(Source):
    name = "wam"
    label = "WW3"
    products = ("waves",)
    nominal_resolution_m = 10000.0


@dataclass
class FakeOverlay:
    name: str
    run: str
    grid: RegularGrid
    footprint: BBox
    products: tuple = ("waves",)

    def fields(self, times, t_index):
        return _waves(self.grid, 1.0)


def _decode_hs(rgb):
    v = rgb[..., 0].astype(float) * 0.1
    v[rgb[..., 0] == 255] = np.nan
    return v


def test_overlay_replaces_base_where_it_has_data(tmp_path):
    base = RegularGrid(LCC.to_wkt(), -500000.0, 10000.0, 60, -100000.0, 10000.0, 40, 10000.0)
    # 1 km overlay covering a small part of the dev area
    fine = RegularGrid(LCC.to_wkt(), -330000.0, 1000.0, 60, -10000.0, 1000.0, 50, 1000.0)
    ov = FakeOverlay("fine", "20261127T06Z", fine, footprint_bbox(fine))
    times = [t(27, 6) + timedelta(hours=h) for h in range(2)]
    run = Run("wam", "20261127T06Z", times[0], "fake://", times)
    sub = Subset(
        base,
        times,
        iter([(i, _waves(base, 2.0)) for i in range(2)]),
        overlays=[ov],
        detail_max_zoom=7,
    )
    st = LocalStorage(tmp_path / "out")
    meta = build_run(WaveSource(), run, sub, "dev", AREA, st, tmp_path / "state")
    p = meta["products"]["waves"]
    assert p["maxzoom"] == 7  # detail zoom added
    # detail-zoom tiles exist only around the overlay
    z7 = [f for f in (tmp_path / "out").rglob("*.png") if "/7/" in str(f)]
    fx0, fx1, fy0, fy1 = mercator.tile_range(ov.footprint, 7)
    assert z7 and all(fx0 <= int(f.parent.name) <= fx1 for f in z7)
    # a tile covering the overlay shows overlay values (1 m) there and base values (2 m) elsewhere
    seen = set()
    for f in (tmp_path / "out").rglob("*.png"):
        hs = _decode_hs(read_png(f.read_bytes()))
        seen |= set(np.round(hs[np.isfinite(hs)], 1).tolist())
    assert {1.0, 2.0} <= seen


def test_coarse_ocean_model_follows_reference_coastline(tmp_path):
    coarse = RegularGrid(LCC.to_wkt(), -500000.0, 20000.0, 30, -100000.0, 20000.0, 20, 20000.0)
    # own (blocky) mask: east half land
    times = [t(27, 6)]
    run = Run("wam", "20261127T06Z", times[0], "fake://", times)
    sub = Subset(coarse, times, iter([(0, _waves(coarse, 3.0, slice(15, None)))]))
    # reference coastline (finer): sea only in the west third
    ref = RegularGrid(LCC.to_wkt(), -500000.0, 5000.0, 120, -100000.0, 5000.0, 80, 5000.0)
    sea = np.zeros((ref.ny, ref.nx), dtype=np.float32)
    sea[:, :50] = 1.0  # x < -250 km is sea
    st = LocalStorage(tmp_path / "out")
    build_run(
        WaveSource(), run, sub, "dev", AREA, st, tmp_path / "state", sea_mask=SeaMask(ref, sea)
    )
    lon_ref, _ = ref.lonlat()
    sea_lon_max = float(np.max(lon_ref[:, 49]))
    for f in (tmp_path / "out").rglob("*.png"):
        z, x, y = (int(v) for v in f.with_suffix("").parts[-3:])
        hs = _decode_hs(read_png(f.read_bytes()))
        lon, lat = mercator.tile_pixel_lonlat(z, x, y)
        lon2 = np.broadcast_to(lon, hs.shape)
        # no values east of the reference coastline (+ one coarse cell for interpolation)
        assert not np.isfinite(hs[lon2 > sea_lon_max + 0.6]).any()
        # where there are values they are the (extrapolated) model value
        assert np.allclose(hs[np.isfinite(hs)], 3.0, atol=0.05)


def test_stray_fjord_cells_are_dropped_and_extrapolation_is_short():
    from weather_layers.build import fill_nearest, open_sea

    valid = np.zeros((20, 20), bool)
    valid[:, :8] = True  # open sea
    valid[10, 15] = True  # a stray "sea" cell deep inside a fjord
    sea = open_sea(valid, min_cells=5)
    assert sea[:, :8].all() and not sea[10, 15]
    arr = np.where(sea, 2.0, np.nan)
    filled = fill_nearest(arr, 1.5)
    assert np.isfinite(filled[:, 8]).all()  # one cell over the coast
    assert np.isnan(filled[:, 10]).all()  # but not deep inland


def test_grow_mean_extrapolates_one_smooth_ring():
    from weather_layers.build import grow_mean

    a = np.full((5, 5), np.nan, dtype=np.float32)
    a[:, 0] = 1.0
    a[:, 1] = 3.0
    g = grow_mean(a, 1)
    assert np.allclose(g[1:4, 2], 3.0) and np.isnan(g[:, 3]).all()
