import numpy as np
from pyproj import CRS, Transformer

from weather_layers import mercator as m
from weather_layers.grids import RegularGrid, Sampler, coarsen_field

LCC = CRS.from_proj4("+proj=lcc +lat_0=63.3 +lon_0=15 +lat_1=63.3 +lat_2=63.3 +R=6371000")


def test_tile_range_and_pixel_centres():
    bbox = m.BBox(7.5, 63.2, 10.0, 64.2)
    x0, x1, y0, y1 = m.tile_range(bbox, 7)
    assert (x0, x1) == (66, 67)
    lon, lat = m.tile_pixel_lonlat(7, x0, y0)
    assert lon.shape == (m.IMAGE_SIZE,) and lat.shape == (m.IMAGE_SIZE,)
    b = m.tile_bounds(7, x0, y0)
    # first data pixel centre is half a pixel inside the tile's west/north edge
    assert b.west < lon[m.BUFFER] < b.west + (b.east - b.west) / 256
    assert b.north > lat[m.BUFFER] > b.north - (b.north - b.south) / 200
    # buffer pixel lies outside the tile
    assert lon[0] < b.west and lat[0] > b.north
    assert np.all(np.diff(lat) < 0)


def test_mercator_roundtrip():
    lon = np.array([-170.0, 0.0, 8.5, 31.5])
    lat = np.array([-60.0, 0.0, 63.7, 71.5])
    x, y = m.lonlat_to_mercator01(lon, lat)
    lon2, lat2 = m.mercator01_to_lonlat(x, y)
    np.testing.assert_allclose(lon2, lon, atol=1e-9)
    np.testing.assert_allclose(lat2, lat, atol=1e-9)


def _lcc_grid(nx=40, ny=30, dx=2500.0):
    return RegularGrid(LCC.to_wkt(), -300000.0, dx, nx, -330000.0, dx, ny, dx)


def test_regrid_linear_field_is_exact_at_known_points():
    """A field linear in projected x,y must be reproduced exactly by bilinear sampling."""
    g = _lcc_grid()
    X, Y = np.meshgrid(g.x(), g.y())
    field = (0.001 * X + 0.002 * Y).astype(np.float64)
    to_ll = Transformer.from_crs(LCC, 4326, always_xy=True)
    # points strictly inside the grid
    px = np.array([-290000.0, -260500.0, -230123.0])
    py = np.array([-320000.0, -300250.0, -290777.0])
    lon, lat = to_ll.transform(px, py)
    s = Sampler.build(g, np.asarray(lon), np.asarray(lat))
    out = s.sample(field[np.newaxis])[0]
    np.testing.assert_allclose(out, 0.001 * px + 0.002 * py, rtol=1e-6)


def test_regrid_cell_centre_returns_cell_value():
    g = _lcc_grid()
    field = np.arange(g.nx * g.ny, dtype=np.float32).reshape(g.ny, g.nx)
    lon2d, lat2d = g.lonlat()
    s = Sampler.build(g, lon2d[5:7, 10:12], lat2d[5:7, 10:12])
    np.testing.assert_allclose(s.sample(field), field[5:7, 10:12], atol=1e-3)


def test_nodata_handling_and_outside_domain():
    g = _lcc_grid()
    field = np.ones((g.ny, g.nx), dtype=np.float32)
    field[:, 20:] = np.nan  # "land" on the east half
    lon2d, lat2d = g.lonlat()
    s = Sampler.build(g, lon2d[10, 17:23], lat2d[10, 17:23])
    out = s.sample(field)
    assert np.all(out[:3] == 1.0)
    assert np.all(np.isnan(out[3:]))
    # far outside the grid -> no data
    s2 = Sampler.build(g, np.array([-40.0]), np.array([10.0]))
    assert np.isnan(s2.sample(field)[0])


def test_coarsen_field_nan_aware():
    f = np.ones((4, 4), dtype=np.float32)
    f[0, 0] = np.nan
    f[2:, 2:] = np.nan
    out = coarsen_field(f, 2)
    assert out[0, 0] == 1.0 and np.isnan(out[1, 1]) and out.shape == (2, 2)


def test_geographic_periodic_grid():
    g = RegularGrid(
        CRS.from_epsg(4326).to_wkt(), 0.0, 0.25, 1440, 90.0, -0.25, 721, 25000.0, periodic_lon=True
    )
    fi, fj = g.fractional_index(np.array([-10.0, 8.0, 359.75]), np.array([63.75, 63.75, 0.0]))
    np.testing.assert_allclose(fi, [1400.0, 32.0, 1439.0])
    np.testing.assert_allclose(fj, [105.0, 105.0, 360.0])
