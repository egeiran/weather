import struct

import numpy as np

from weather_layers.dap import decode_dods, grid_names, hyperslab, parse_das

DDS = """Dataset {
    Float64 time[time = 2];
    Structure {
        Float32 x_wind_10m[time = 2][height7 = 1][y = 2][x = 3];
    } x_wind_10m;
    Byte mask[y = 2][x = 3];
    Int16 level[level = 2];
} test;"""


def _payload():
    body = b""
    t = np.array([1.0, 2.0], dtype=">f8")
    body += struct.pack(">II", 2, 2) + t.tobytes()
    w = np.arange(12, dtype=">f4")
    body += struct.pack(">II", 12, 12) + w.tobytes()
    mask = bytes([1, 0, 1, 1, 0, 0])
    body += struct.pack(">II", 6, 6) + mask + b"\x00\x00"  # padded to 8
    lev = np.array([5, -7], dtype=">i4")
    body += struct.pack(">II", 2, 2) + lev.tobytes()
    return DDS.encode() + b"\nData:\n" + body


def test_decode_dods():
    out = decode_dods(_payload())
    assert out["time"].tolist() == [1.0, 2.0]
    assert out["x_wind_10m"].shape == (2, 1, 2, 3)
    assert out["x_wind_10m"].dtype == np.float32
    assert out["x_wind_10m"][1, 0, 1, 2] == 11
    assert out["mask"].tolist() == [[1, 0, 1], [1, 0, 0]]
    assert out["level"].tolist() == [5, -7] and out["level"].dtype == np.int16


def test_parse_das_and_grids():
    das = """Attributes {
    x_wind_10m {
        Float32 _FillValue 9.96921e+36;
        String units "m/s";
        String standard_name "x_wind";
    }
    projection_lambert {
        Float64 standard_parallel 63.3, 63.3;
        String proj4 "+proj=lcc +lat_0=63.3";
    }
}"""
    a = parse_das(das)
    assert a["x_wind_10m"]["units"] == "m/s"
    assert a["x_wind_10m"]["_FillValue"] > 1e36
    assert a["projection_lambert"]["standard_parallel"] == [63.3, 63.3]
    dds = """Dataset {
    Float32 x[x = 3];
    Grid {
     ARRAY:
        Float32 hs[time = 1][y = 2][x = 3];
     MAPS:
        Float64 time[time = 1];
    } hs;
} d;"""
    assert grid_names(dds) == {"hs"}
    assert hyperslab((0, 10), 3, (5, 20, 2)) == "[0:10][3][5:2:20]"
