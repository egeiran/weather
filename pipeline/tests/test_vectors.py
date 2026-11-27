import numpy as np
from pyproj import CRS, Transformer

from weather_layers import vectors as vec

MEPS_LCC = CRS.from_proj4("+proj=lcc +lat_0=63.3 +lon_0=15 +lat_1=63.3 +lat_2=63.3 +R=6371000")


def test_direction_conventions():
    # Wind blowing towards the east (u>0) comes FROM the west (270); a current with the same
    # motion flows TO the east (90).
    assert vec.from_direction(np.array(5.0), np.array(0.0)) == 270.0
    assert vec.to_direction(np.array(5.0), np.array(0.0)) == 90.0
    # Northerly wind (from north) moves south: v < 0
    u, v = vec.uv_from_from_direction(np.array(10.0), np.array(0.0))
    assert abs(u) < 1e-9 and v == -10.0
    # Current going to north-east
    u, v = vec.uv_from_to_direction(np.array(1.0), np.array(45.0))
    np.testing.assert_allclose([u, v], [np.sqrt(0.5), np.sqrt(0.5)])


def test_roundtrip_speed_direction():
    rng = np.random.default_rng(1)
    u, v = rng.normal(size=1000) * 10, rng.normal(size=1000) * 10
    d = vec.from_direction(u, v)
    u2, v2 = vec.uv_from_from_direction(vec.speed(u, v), d)
    np.testing.assert_allclose(u2, u, atol=1e-9)
    np.testing.assert_allclose(v2, v, atol=1e-9)


def test_grid_angle_lcc_matches_analytic_convergence():
    # For a tangent Lambert conformal cone, the grid north deviates from true north by
    # n * (lon - lon0) with n = sin(lat_1).
    to_xy = Transformer.from_crs(4326, MEPS_LCC, always_xy=True)
    lons = np.array([5.0, 15.0, 25.0, 30.0])
    lats = np.array([60.0, 65.0, 69.5, 70.0])
    x, y = to_xy.transform(lons, lats)
    alpha = vec.grid_north_angle(MEPS_LCC, np.asarray(x), np.asarray(y))
    n = np.sin(np.radians(63.3))
    # East of the central meridian the grid x-axis points south of true east (alpha < 0).
    expected = np.radians(-n * (lons - 15.0))
    np.testing.assert_allclose(alpha, expected, atol=np.radians(0.05))
    assert alpha[0] > 0 > alpha[2]  # west of lon0: x-axis tilted north; east: tilted south


def test_rotation_recovers_true_wind_on_synthetic_grid():
    # A true westerly wind (towards east) expressed in grid components at a point east of the
    # central meridian, rotated back, must come out as a westerly again.
    to_xy = Transformer.from_crs(4326, MEPS_LCC, always_xy=True)
    x, y = to_xy.transform(np.array([25.0]), np.array([69.5]))
    alpha = vec.grid_north_angle(MEPS_LCC, np.asarray(x), np.asarray(y))
    u_true, v_true = np.array([8.0]), np.array([3.0])
    # project the true vector onto grid axes (inverse rotation)
    ca, sa = np.cos(alpha), np.sin(alpha)
    gx = u_true * ca + v_true * sa
    gy = -u_true * sa + v_true * ca
    u, v = vec.rotate_grid_to_earth(gx, gy, alpha)
    np.testing.assert_allclose([u[0], v[0]], [8.0, 3.0], atol=1e-9)
    # And skipping the rotation would be wrong by the convergence angle (~8.5 deg here)
    err = abs(vec.from_direction(gx, gy) - vec.from_direction(u_true, v_true))[0]
    assert 7.0 < err < 10.0
