"""Merged point series: one small file per chunk of lattice cells, all variables, whole timeline.

A click on the map costs one request: the chunk containing the clicked cell.

Chunk file format "WLS1" (gzip-compressed):
    bytes 0..3   b"WLS1"
    uint16 LE    rows (cells, south->north), cols (cells, west->east), nvars, ntimes
    uint8 data   [var][row][col][time], code 255 = no data, value = offset + scale * code
The variable list, time axis and encodings live in the manifest (`series`).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import struct
from datetime import datetime
from pathlib import Path

import numpy as np

from . import encoding as enc
from .availability import encode_bits
from .log import step
from .products import PRODUCTS
from .seriesgrid import CHUNK, SeriesWindow
from .sources.base import iso
from .stitch import _parse, stitch
from .storage import LocalStorage

MAGIC = b"WLS1"
SERIES_PRODUCTS = ("wind", "waves", "swell", "current")


def ocean_only(window: SeriesWindow) -> bool:
    """Large areas keep only chunks touching ocean-model data (decision 0003)."""
    env = os.environ.get("WEATHER_LAYERS_SERIES_OCEAN_ONLY", "auto")
    if env == "auto":
        return window.ny * window.nx > 200_000
    return env not in ("0", "false", "no")


def series_id(runs: dict[str, dict], area: str) -> str:
    key = json.dumps({"area": area, "runs": {s: m["run_id"] for s, m in sorted(runs.items())}})
    return hashlib.sha1(key.encode()).hexdigest()[:12]


def encode_chunk(block: np.ndarray) -> bytes:
    """block: uint8 [nvars, rows, cols, ntimes]."""
    nv, rows, cols, nt = block.shape
    header = MAGIC + struct.pack("<HHHH", rows, cols, nv, nt)
    return gzip.compress(header + np.ascontiguousarray(block).tobytes(), compresslevel=9, mtime=0)


def decode_chunk(data: bytes) -> np.ndarray:
    raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
    if raw[:4] != MAGIC:
        raise ValueError("not a WLS1 chunk")
    rows, cols, nv, nt = struct.unpack("<HHHH", raw[4:12])
    return np.frombuffer(raw[12:], dtype=np.uint8).reshape(nv, rows, cols, nt)


def build_series(
    runs: dict[str, dict],
    area_name: str,
    window: SeriesWindow,
    storage: LocalStorage,
    state_dir: Path,
) -> dict | None:
    """Stitch all sources' series state into chunk files. Returns the manifest `series` entry."""
    sid = series_id(runs, area_name)
    final = f"series/{sid}"
    # Variables in a fixed order, with their stitched segments.
    variables = []
    plans = []  # (var index, product, channel index, [(source, run_id, times)])
    union: set[datetime] = set()
    for pname in SERIES_PRODUCTS:
        segs = stitch(pname, runs)
        if not segs:
            continue
        for ci, ch in enumerate(PRODUCTS[pname].channels):
            vi = len(variables)
            variables.append(
                {
                    **ch.to_manifest(),
                    "product": pname,
                    "segments": [
                        {
                            "source": s.source,
                            "run_id": s.run_id,
                            "start": iso(s.times[0]),
                            "end": iso(s.times[-1]),
                            "step_hours": s.step_hours,
                        }
                        for s in segs
                    ],
                }
            )
            plans.append((vi, pname, ci, segs))
        for s in segs:
            union.update(s.times)
    if not variables:
        return None
    times = sorted(union)
    tindex = {t: i for i, t in enumerate(times)}
    entry = {
        "id": sid,
        "template": f"{final}/{{cy}}/{{cx}}.bin",
        "format": "WLS1+gzip",
        "grid": window.to_manifest(),
        "times": [iso(t) for t in times],
        "variables": variables,
    }
    if storage.exists(f"{final}/series.json"):
        cached = json.loads(storage.read_bytes(f"{final}/series.json") or b"{}")
        if cached.get("id") == sid:
            return cached

    # Open the per-source state arrays (memory-mapped) once.
    state: dict[tuple[str, str], tuple[np.ndarray, SeriesWindow, dict[datetime, int]]] = {}
    for _, pname, _, segs in plans:
        for s in segs:
            key = (s.source, pname)
            if key in state:
                continue
            sdir = state_dir / s.source / s.run_id
            meta = json.loads((sdir / "series.json").read_text())
            g = meta["grid"] if "grid" in meta else meta["window"]
            src_window = SeriesWindow(g["row0"], g["col0"], g["rows"], g["cols"])
            arr = np.load(sdir / f"{pname}.npy", mmap_mode="r")
            src_times = {_parse(t): i for i, t in enumerate(meta["times"])}
            state[key] = (arr, src_window, src_times)

    staging = storage.staging_prefix(final)
    nv, nt = len(variables), len(times)
    only_ocean = ocean_only(window)
    ocean_vars = [vi for vi, pname, _, _ in plans if PRODUCTS[pname].ocean]
    entry["ocean_only"] = only_ocean
    present: list[tuple[int, int]] = []
    with step("series", id=sid, variables=nv, times=nt, rows=window.ny, cols=window.nx) as info:
        for band in range(0, window.ny, CHUNK):
            band_win = SeriesWindow(window.r0 + band, window.c0, CHUNK, window.nx)
            out = np.full((nv, CHUNK, window.nx, nt), enc.NODATA, dtype=np.uint8)
            for vi, pname, ci, segs in plans:
                for s in segs:
                    arr, src_win, src_times = state[(s.source, pname)]
                    ov = band_win.intersect(src_win)
                    if ov is None:
                        continue
                    rs, cs, srs, scs = ov
                    src_idx = [src_times[t] for t in s.times if t in src_times]
                    dst_idx = [tindex[t] for t in s.times if t in src_times]
                    if not src_idx:
                        continue
                    block = np.asarray(arr[src_idx, ci, srs, scs])  # [T, r, c]
                    out[vi, rs, cs][..., dst_idx] = np.moveaxis(block, 0, -1)
            for c in range(0, window.nx, CHUNK):
                block = out[:, :, c : c + CHUNK, :]
                if (block == enc.NODATA).all():
                    continue
                if only_ocean and ocean_vars and (block[ocean_vars] == enc.NODATA).all():
                    continue
                cy = (window.r0 + band) // CHUNK
                cx = (window.c0 + c) // CHUNK
                storage.write_bytes(f"{staging}/{cy}/{cx}.bin", encode_chunk(block))
                present.append((cx, cy))
        info["chunks"] = len(present)
    cy0, cx0 = window.r0 // CHUNK, window.c0 // CHUNK
    cy1 = (window.r0 + window.ny) // CHUNK - 1
    cx1 = (window.c0 + window.nx) // CHUNK - 1
    entry["availability"] = encode_bits(cx0, cy0, cx1, cy1, present)
    storage.write_bytes(f"{staging}/series.json", json.dumps(entry).encode())
    storage.promote(staging, final)
    return entry
