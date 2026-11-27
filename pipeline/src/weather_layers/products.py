"""Products: how source fields become the three channels of a value tile.

A product has *inputs* (native-grid arrays derived from source fields, interpolated
independently) and *outputs* (channels computed from the interpolated inputs). Vector
quantities are interpolated as east/north components and only converted to speed and
direction after interpolation, so directions interpolate correctly across the 0/360 wrap.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from . import encoding as enc
from . import vectors as vec

Fields = dict[str, np.ndarray]


@dataclass(frozen=True)
class Product:
    name: str
    channels: tuple[enc.ChannelSpec, enc.ChannelSpec, enc.ChannelSpec]
    inputs: Callable[[Fields], Fields]
    outputs: Callable[[Fields], tuple[np.ndarray, np.ndarray, np.ndarray]]
    # True for ocean products: series sampling may borrow the nearest sea cell at the coast.
    ocean: bool = False


def _wind_inputs(f: Fields) -> Fields:
    return {"u": f["wind_u"], "v": f["wind_v"], "gust": f["wind_gust"]}


def _wind_outputs(s: Fields):
    return vec.speed(s["u"], s["v"]), vec.from_direction(s["u"], s["v"]), s["gust"]


def _dir_inputs(prefix: str):
    """Waves come with a 'from' direction; interpolate unit vectors of the motion."""

    def inputs(f: Fields) -> Fields:
        to_rad = np.radians(f[f"{prefix}_from_direction"] + 180.0)
        return {
            "hs": f[f"{prefix}_height"],
            "tp": f[f"{prefix}_period"],
            "dx": np.sin(to_rad),
            "dy": np.cos(to_rad),
        }

    return inputs


def _wave_outputs(s: Fields):
    return s["hs"], s["tp"], vec.from_direction(s["dx"], s["dy"])


def _current_inputs(f: Fields) -> Fields:
    return {"u": f["current_u"], "v": f["current_v"], "temp": f["sea_temperature"]}


def _current_outputs(s: Fields):
    spd_kn = vec.speed(s["u"], s["v"]) * vec.KNOTS_PER_MS
    return spd_kn, vec.to_direction(s["u"], s["v"]), s["temp"]


def _named(spec: enc.ChannelSpec, name: str, description: str) -> enc.ChannelSpec:
    return enc.ChannelSpec(name, spec.unit, spec.scale, spec.offset, spec.wrap, description)


WIND = Product("wind", (enc.WIND_SPEED, enc.WIND_FROM, enc.GUST), _wind_inputs, _wind_outputs)
WAVES = Product(
    "waves",
    (
        _named(enc.WAVE_HS, "wave_height", "significant wave height (total sea)"),
        _named(enc.WAVE_PERIOD, "wave_period", "peak wave period (total sea)"),
        _named(enc.WAVE_FROM, "wave_from_direction", "mean wave direction, coming from"),
    ),
    _dir_inputs("wave"),
    _wave_outputs,
    ocean=True,
)
SWELL = Product(
    "swell",
    (
        _named(enc.WAVE_HS, "swell_height", "significant wave height of swell"),
        _named(enc.WAVE_PERIOD, "swell_period", "swell period"),
        _named(enc.WAVE_FROM, "swell_from_direction", "swell direction, coming from"),
    ),
    _dir_inputs("swell"),
    _wave_outputs,
    ocean=True,
)
CURRENT = Product(
    "current",
    (enc.CURRENT_SPEED, enc.CURRENT_TO, enc.SEA_TEMP),
    _current_inputs,
    _current_outputs,
    ocean=True,
)

PRODUCTS = {p.name: p for p in (WIND, WAVES, SWELL, CURRENT)}

# Which source fields each product needs (used by sources to decide what to fetch).
PRODUCT_FIELDS = {
    "wind": ("wind_u", "wind_v", "wind_gust"),
    "waves": ("wave_height", "wave_period", "wave_from_direction"),
    "swell": ("swell_height", "swell_period", "swell_from_direction"),
    "current": ("current_u", "current_v", "sea_temperature"),
}
