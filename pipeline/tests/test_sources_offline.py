"""Offline tests for source-specific parsing, grids and conventions (no network)."""

import json

import numpy as np
from pyproj import CRS, Transformer

from weather_layers import products
from weather_layers.grids import RegularGrid, Sampler
from weather_layers.sources.ecmwf import NI, NJ, decode_grib, parse_index, steps_00_12
from weather_layers.sources.projected import cf_crs
from weather_layers.vectors import KNOTS_PER_MS


def _grib(values: np.ndarray, bitmap: np.ndarray | None = None) -> bytes:
    import eccodes

    h = eccodes.codes_grib_new_from_samples("regular_ll_sfc_grib2")
    try:
        for k, v in {
            "Ni": NI, "Nj": NJ,
            "latitudeOfFirstGridPointInDegrees": 90.0,
            "longitudeOfFirstGridPointInDegrees": 180.0,
            "latitudeOfLastGridPointInDegrees": -90.0,
            "longitudeOfLastGridPointInDegrees": 179.75,
            "iDirectionIncrementInDegrees": 0.25,
            "jDirectionIncrementInDegrees": 0.25,
        }.items():
            eccodes.codes_set(h, k, v)
        if bitmap is not None:
            eccodes.codes_set(h, "bitmapPresent", 1)
            eccodes.codes_set(h, "missingValue", 9999.0)
            values = np.where(bitmap, values, 9999.0)
        eccodes.codes_set_values(h, values.ravel())
        return eccodes.codes_get_message(h)
    finally:
        eccodes.codes_release(h)


def test_ecmwf_grib_layout_and_bitmap():
    lat = 90 - 0.25 * np.arange(NJ)[:, None]
    lon = ((180 + 0.25 * np.arange(NI)[None, :] + 180) % 360) - 180  # first column = 180E = -180
    field = (lat + 0 * lon).astype(np.float64)  # value = latitude
    mask = np.ones((NJ, NI), bool)
    mask[100, 700] = False  # a "land" point
    out = decode_grib(_grib(field, mask))
    assert out.shape == (NJ, NI)
    assert abs(out[0, 0] - 90) < 0.1 and abs(out[-1, 0] + 90) < 0.1
    assert np.isnan(out[100, 700]) and np.isfinite(out[100, 701])


def test_ecmwf_index_and_steps():
    lines = [
        {"param": "10u", "levtype": "sfc", "_offset": 0, "_length": 10},
        {"param": "z", "levtype": "pl", "levelist": "500", "_offset": 10, "_length": 5},
        {"param": "10fg3", "levtype": "sfc", "_offset": 15, "_length": 7},
    ]
    idx = parse_index("\n".join(json.dumps(x) for x in lines))
    assert set(idx) == {"10u", "10fg3"}
    s = steps_00_12()
    assert s[:3] == [0, 3, 6] and 144 in s and 147 not in s and 150 in s and s[-1] == 360


def test_rotated_pole_grid_regrid_matches_projection():
    # WW3 4 km grid mapping (CF attributes as served)
    crs = cf_crs({"grid_mapping_name": "rotated_latitude_longitude",
                  "grid_north_pole_longitude": 140.0, "grid_north_pole_latitude": 22.0,
                  "earth_radius": 6371000.0})
    g = RegularGrid(crs.to_wkt(), 5.53, 0.04, 624, -14.35, 0.04, 1026, 4400.0)
    lon2d, lat2d = g.lonlat()
    # Frøya offshore cell from the spike: j=450, i=340 -> 63.9034N 8.0290E
    assert abs(lat2d[450, 340] - 63.9034) < 2e-3 and abs(lon2d[450, 340] - 8.0290) < 2e-3
    field = np.arange(g.nx * g.ny, dtype=np.float32).reshape(g.ny, g.nx)
    s = Sampler.build(g, lon2d[450:451, 340:341], lat2d[450:451, 340:341])
    assert s.sample(field)[0, 0] == field[450, 340]


def test_norkyst_polar_stereographic_on_wgs84():
    attrs = {"grid_mapping_name": "polar_stereographic",
             "straight_vertical_longitude_from_pole": 70.0, "latitude_of_projection_origin": 90.0,
             "standard_parallel": 60.0, "false_easting": 3369600.0, "false_northing": 1844800.0,
             "semi_major_axis": 6378137.0, "semi_minor_axis": 6356752.3142}
    crs = cf_crs(attrs)
    # Frøya cell from the spike: Y=657, X=1149 -> 63.7476N 8.2963E
    to_ll = Transformer.from_crs(crs, CRS.from_epsg(4326), always_xy=True)
    lon, lat = to_ll.transform(1149 * 800.0, 657 * 800.0)
    assert abs(lat - 63.7476) < 1e-3 and abs(lon - 8.2963) < 1e-3


def test_wave_directions_interpolate_across_north():
    p = products.WAVES
    f = {"wave_height": np.array([[1.0, 3.0]]), "wave_period": np.array([[8.0, 10.0]]),
         "wave_from_direction": np.array([[350.0, 10.0]])}
    inp = p.inputs(f)
    mid = {k: v.mean(axis=1) for k, v in inp.items()}  # halfway between the two cells
    hs, tp, d = p.outputs(mid)
    assert abs(hs[0] - 2.0) < 1e-9 and abs(tp[0] - 9.0) < 1e-9
    assert min(d[0], 360 - d[0]) < 1e-6  # from north, not from south (naive mean = 180)


def test_current_speed_in_knots_and_to_direction():
    p = products.CURRENT
    out = p.outputs({"u": np.array([0.0]), "v": np.array([1.0]), "temp": np.array([8.0])})
    assert abs(out[0][0] - KNOTS_PER_MS) < 1e-9  # 1 m/s = 1.944 kn
    assert abs(out[1][0] - 0.0) < 1e-9  # flowing TO north
