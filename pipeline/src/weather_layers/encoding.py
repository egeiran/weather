"""Value encoding: physical values <-> 8-bit codes in RGB PNG channels.

Every data channel is linear: value = offset + scale * code, for code in 0..254. Code 255 is
reserved for "no data" (land for ocean models, outside the model domain, missing values).
Directional channels wrap: scale = 360/255, so codes 0..254 cover 0..358.6 degrees.

Alpha is never used for data: browsers premultiply alpha when decoding images, which would
corrupt values on semi-transparent pixels. Tiles are written as RGB (alpha implicitly 255).
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import numpy as np
from PIL import Image

NODATA = 255
MAX_CODE = 254


@dataclass(frozen=True)
class ChannelSpec:
    name: str
    unit: str
    scale: float
    offset: float = 0.0
    wrap: float | None = None  # e.g. 360 for directions
    description: str = ""

    @property
    def max_value(self) -> float:
        return self.offset + self.scale * MAX_CODE

    def to_manifest(self) -> dict:
        d = {
            "name": self.name,
            "unit": self.unit,
            "scale": self.scale,
            "offset": self.offset,
            "nodata": NODATA,
            "min": self.offset,
            "max": round(self.max_value, 6),
        }
        if self.wrap is not None:
            d["wrap"] = self.wrap
        if self.description:
            d["description"] = self.description
        return d


def encode(values: np.ndarray, spec: ChannelSpec) -> np.ndarray:
    """Quantise float values (NaN = no data) to uint8 codes."""
    v = np.asarray(values, dtype=np.float64)
    nan = ~np.isfinite(v)
    if spec.wrap is not None:
        codes = np.rint(np.mod(np.where(nan, 0.0, v), spec.wrap) / spec.scale)
        codes = np.mod(codes, round(spec.wrap / spec.scale))
    else:
        codes = np.rint((np.where(nan, spec.offset, v) - spec.offset) / spec.scale)
        codes = np.clip(codes, 0, MAX_CODE)
    out = codes.astype(np.uint8)
    out[nan] = NODATA
    return out


def decode(codes: np.ndarray, spec: ChannelSpec) -> np.ndarray:
    c = np.asarray(codes)
    v = spec.offset + spec.scale * c.astype(np.float64)
    return np.where(c == NODATA, np.nan, v)


def png_bytes(rgb: np.ndarray, compress_level: int = 9) -> bytes:
    """Encode an (H, W, 3) uint8 array as an RGB PNG with no colour-management chunks."""
    if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("expected (H, W, 3) uint8")
    buf = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(buf, format="PNG", compress_level=compress_level)
    return buf.getvalue()


def read_png(data: bytes) -> np.ndarray:
    with Image.open(io.BytesIO(data)) as im:
        return np.asarray(im.convert("RGB"))


# --- channel catalogue (shared by all sources; precision targets in comments) ------------

DIR_SCALE = 360.0 / 255.0  # 1.41 deg step, max error 0.71 deg (target <= 2 deg)

WIND_SPEED = ChannelSpec("wind_speed", "m/s", 0.2, description="10 m wind speed")  # err 0.1
WIND_FROM = ChannelSpec(
    "wind_from_direction",
    "deg",
    DIR_SCALE,
    wrap=360.0,
    description="10 m wind direction, coming from, clockwise from north",
)
GUST = ChannelSpec("wind_gust", "m/s", 0.25, description="10 m wind gust")  # err 0.125
WAVE_HS = ChannelSpec("wave_height", "m", 0.1, description="significant wave height")  # err 0.05
WAVE_PERIOD = ChannelSpec("wave_period", "s", 0.1, description="wave period")  # err 0.05
WAVE_FROM = ChannelSpec(
    "wave_from_direction",
    "deg",
    DIR_SCALE,
    wrap=360.0,
    description="wave direction, coming from, clockwise from north",
)
CURRENT_SPEED = ChannelSpec(
    "current_speed", "kn", 0.04, description="surface current speed"
)  # err 0.02 kn
CURRENT_TO = ChannelSpec(
    "current_to_direction",
    "deg",
    DIR_SCALE,
    wrap=360.0,
    description="surface current direction, going to, clockwise from north",
)
SEA_TEMP = ChannelSpec(
    "sea_temperature", "degC", 0.15, offset=-3.0, description="sea surface temperature"
)  # err 0.075
