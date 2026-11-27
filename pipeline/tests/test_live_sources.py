"""Live checks against MET Norway (deselected by default; run with `pytest -m live`)."""

from pathlib import Path

import numpy as np
import pytest

from weather_layers.config import DEFAULT_USER_AGENT
from weather_layers.dap import DapDataset
from weather_layers.http import HttpClient
from weather_layers.sources.meps import Meps
from weather_layers.vectors import from_direction, grid_north_angle, rotate_grid_to_earth

pytestmark = pytest.mark.live


def test_meps_rotation_matches_met_wind_direction(tmp_path: Path):
    """Our rotated x/y wind must reproduce MET's own wind_direction (from, true north)."""
    http = HttpClient(DEFAULT_USER_AGENT, cache_dir=tmp_path)
    src = Meps(cache=True)
    run = src.latest_complete_run(http)
    assert run is not None
    ds = DapDataset(http, run.url)
    grid = src.grid(ds)
    # Finnmark (far east of lon0 = 15E): convergence ~ +9 deg
    sl = "[12][0][819:823][578:582]"
    got = {
        v: ds.unpack(v, ds.fetch({v: sl})[v])[0, 0]
        for v in ("x_wind_10m", "y_wind_10m", "wind_direction")
    }
    sub = grid.subset(819, 824, 578, 583)
    X, Y = np.meshgrid(sub.x(), sub.y())
    alpha = grid_north_angle(sub.crs, X, Y)
    u, v = rotate_grid_to_earth(got["x_wind_10m"], got["y_wind_10m"], alpha)
    ours = from_direction(u, v)
    diff = np.abs((ours - got["wind_direction"] + 180) % 360 - 180)
    assert diff.max() < 0.5, diff
    unrotated = from_direction(got["x_wind_10m"], got["y_wind_10m"])
    diff_unrot = np.abs((unrotated - got["wind_direction"] + 180) % 360 - 180)
    assert diff_unrot.mean() > 5.0  # proves the rotation matters here
