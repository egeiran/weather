from datetime import timedelta

import numpy as np

from weather_layers.availability import decode_bits, encode_bits
from weather_layers.mercator import BBox
from weather_layers.series import decode_chunk, encode_chunk
from weather_layers.seriesgrid import SeriesWindow, cell_of
from weather_layers.sources.base import iso
from weather_layers.stitch import stitch

from .fakes import t


def _meta(source, run_id, times, products):
    return {
        "run_id": run_id,
        "times": [iso(x) for x in times],
        "products": {p: {} for p in products},
    }


def test_stitch_priority_and_step_segments():
    meps_t = [t(27, 6) + timedelta(hours=h) for h in range(67)]
    ec_ref = t(27, 0)
    ec_steps = list(range(48, 145, 3)) + list(range(150, 241, 6))
    ec_t = [ec_ref + timedelta(hours=s) for s in ec_steps]
    runs = {
        "meps": _meta("meps", "20261127T06Z", meps_t, ["wind"]),
        "ecmwf": _meta("ecmwf", "20261127T00Z", ec_t, ["wind", "waves"]),
    }
    segs = stitch("wind", runs)
    assert [(s.source, s.step_hours) for s in segs] == [
        ("meps", 1.0),
        ("ecmwf", 3.0),
        ("ecmwf", 6.0),
    ]
    assert segs[0].times[-1] == meps_t[-1]
    assert segs[1].times[0] == meps_t[-1] + timedelta(hours=3)  # strictly after MEPS end
    assert segs[2].times[0] == ec_ref + timedelta(hours=150)
    assert segs[-1].times[-1] == ec_ref + timedelta(hours=240)
    # waves without WW3: ECMWF covers everything it has
    w = stitch("waves", runs)
    assert w[0].source == "ecmwf" and w[0].times[0] == ec_t[0]
    # swell: no source -> no segments (documented gap)
    assert stitch("swell", runs) == []


def test_chunk_roundtrip_and_gzip_tolerance():
    rng = np.random.default_rng(3)
    block = rng.integers(0, 256, size=(12, 4, 4, 100), dtype=np.uint8)
    data = encode_chunk(block)
    assert data[:2] == b"\x1f\x8b"
    np.testing.assert_array_equal(decode_chunk(data), block)
    import gzip

    np.testing.assert_array_equal(decode_chunk(gzip.decompress(data)), block)


def test_series_window_alignment_and_cell_lookup():
    w = SeriesWindow.for_area(BBox(7.5, 63.2, 10.0, 64.2))
    assert w.r0 % 4 == 0 and w.c0 % 4 == 0 and w.ny % 4 == 0 and w.nx % 4 == 0
    lon, lat = w.lonlat()
    r, c = cell_of(float(lon[5, 7]), float(lat[5, 7]))
    assert (r - w.r0, c - w.c0) == (5, 7)
    assert lat[1, 0] > lat[0, 0]  # rows run south -> north


def test_availability_bits_roundtrip():
    present = {(3, 5), (4, 5), (6, 7)}
    d = encode_bits(3, 5, 6, 7, present)
    assert d["count"] == 3
    assert decode_bits(d) == present
