"""Compact bitsets over a rectangle of tiles/chunks, stored in the manifest.

Lets the client skip requests for tiles that hold no data (e.g. all-land for ocean models),
without listing every tile. Encoding: row-major bits (LSB first within each byte), base64.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable


def encode_bits(x0: int, y0: int, x1: int, y1: int, present: Iterable[tuple[int, int]]) -> dict:
    w, h = x1 - x0 + 1, y1 - y0 + 1
    bits = bytearray((w * h + 7) // 8)
    count = 0
    for x, y in present:
        if x0 <= x <= x1 and y0 <= y <= y1:
            i = (y - y0) * w + (x - x0)
            if not bits[i // 8] & (1 << (i % 8)):
                count += 1
            bits[i // 8] |= 1 << (i % 8)
    return {
        "x0": x0,
        "y0": y0,
        "width": w,
        "height": h,
        "count": count,
        "bits": base64.b64encode(bytes(bits)).decode("ascii"),
    }


def decode_bits(d: dict) -> set[tuple[int, int]]:
    raw = base64.b64decode(d["bits"])
    w = d["width"]
    out = set()
    for i in range(d["width"] * d["height"]):
        if raw[i // 8] & (1 << (i % 8)):
            out.add((d["x0"] + i % w, d["y0"] + i // w))
    return out
