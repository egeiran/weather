import numpy as np
import pytest

from weather_layers import encoding as enc

# (spec, max allowed abs error from the precision targets, test range)
TARGETS = [
    (enc.WIND_SPEED, 0.2, (0.0, 50.0)),
    (enc.GUST, 0.2, (0.0, 63.0)),
    (enc.WAVE_HS, 0.05, (0.0, 25.0)),
    (enc.WAVE_PERIOD, 0.1, (0.0, 25.0)),
    (enc.CURRENT_SPEED, 0.02, (0.0, 10.0)),
    (enc.SEA_TEMP, 0.1, (-2.0, 30.0)),
]


@pytest.mark.parametrize("spec,tol,rng", TARGETS, ids=[t[0].name for t in TARGETS])
def test_roundtrip_within_precision_target(spec, tol, rng):
    values = np.linspace(*rng, 10001)
    decoded = enc.decode(enc.encode(values, spec), spec)
    assert np.nanmax(np.abs(decoded - values)) <= tol + 1e-9


@pytest.mark.parametrize("spec", [enc.WIND_FROM, enc.WAVE_FROM, enc.CURRENT_TO])
def test_direction_roundtrip_wraps(spec):
    values = np.linspace(-720, 720, 20001)
    decoded = enc.decode(enc.encode(values, spec), spec)
    diff = np.abs(((decoded - values) + 180) % 360 - 180)
    assert diff.max() <= 2.0  # precision target
    assert diff.max() <= 0.71
    # 359.9 must encode to 0 (wrap), never to the no-data code
    assert enc.encode(np.array([359.9]), spec)[0] == 0


def test_nodata_and_clipping():
    spec = enc.WAVE_HS
    codes = enc.encode(np.array([np.nan, -1.0, 1000.0, np.inf]), spec)
    assert codes.tolist() == [255, 0, 254, 255]
    assert np.isnan(enc.decode(np.array([255]), spec)[0])


def test_png_roundtrip_is_lossless_and_opaque():
    rng = np.random.default_rng(0)
    rgb = rng.integers(0, 256, size=(258, 258, 3), dtype=np.uint8)
    data = enc.png_bytes(rgb)
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # colour type 2 = RGB (no alpha channel, so no premultiplication issues)
    assert data[25] == 2
    assert b"gAMA" not in data and b"iCCP" not in data and b"sRGB" not in data
    np.testing.assert_array_equal(enc.read_png(data), rgb)
