"""Cross-check published values against MET Norway's point APIs.

Compares our decoded point series (exactly what the client gets on click) with
api.met.no locationforecast/2.0/complete (wind, gust, direction) and oceanforecast/2.0/complete
(wave height and direction, current, sea temperature) at a few coastal points.

Etiquette: identifying User-Agent, coordinates with 4 decimals, responses reused until their
`Expires` header passes (stored under the cache dir), one request at a time.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import numpy as np

from . import mercator
from .config import Settings
from .encoding import read_png
from .http import HttpClient
from .log import log
from .series import decode_chunk
from .vectors import KNOTS_PER_MS, to_direction

LOCATION = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
OCEAN = "https://api.met.no/weatherapi/oceanforecast/2.0/complete"

# Coastal sea points in the development area (Frøya/Hitra, Frohavet, Halten, Smøla side).
POINTS = [
    ("Frøya vest", 63.8000, 8.3000),
    ("Sula", 63.8800, 8.5500),
    ("Froan", 64.0500, 8.9500),
    ("Halten", 64.1500, 9.4500),
    ("Frohavet", 63.8500, 9.2000),
    ("Hitra sørvest", 63.4500, 7.9000),
    ("Grip-retning", 63.4000, 7.6000),
    ("Kya", 64.1000, 9.7500),
]

LEADS_H = (3, 6, 12, 18, 24, 30, 36, 42, 48)


@dataclass
class Pair:
    point: str
    var: str
    time: str
    ours: float
    met: float
    source: str


def _get_json(http: HttpClient, url: str, cache_dir: Path) -> dict:
    """GET with reuse until Expires (MET terms)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    f = cache_dir / (hashlib.sha256(url.encode()).hexdigest()[:24] + ".json")
    if f.exists():
        cached = json.loads(f.read_text())
        if cached["expires"] > time.time():
            return cached["body"]
    r = http.get(url)
    expires = r.headers.get("expires") or r.headers.get("Expires")
    try:
        exp = parsedate_to_datetime(expires).timestamp() if expires else time.time() + 600
    except (TypeError, ValueError):
        exp = time.time() + 600
    body = json.loads(r.content)
    f.write_text(json.dumps({"expires": exp, "body": body}))
    return body


def _series_at(manifest: dict, out_dir: Path, lat: float, lon: float):
    s = manifest["series"]
    g = s["grid"]
    r = math.floor((lat - g["origin"][1]) / g["dlat"])
    c = math.floor((lon - g["origin"][0]) / g["dlon"])
    cy, cx = r // g["chunk"], c // g["chunk"]
    path = out_dir / s["template"].replace("{cy}", str(cy)).replace("{cx}", str(cx))
    if not path.exists():
        return None
    arr = decode_chunk(path.read_bytes())
    row, col = r - cy * g["chunk"], c - cx * g["chunk"]
    out = {}
    for vi, v in enumerate(s["variables"]):
        codes = arr[vi, row, col, :].astype(float)
        vals = v["offset"] + v["scale"] * codes
        vals[codes == v["nodata"]] = np.nan
        out[v["name"]] = vals
    return out


def _time_key(t: str) -> str:
    return t.replace("-", "").replace(":", "")[:13] + "Z"


def _tile_at(manifest: dict, out_dir: Path, layer: str, t: str, lat: float, lon: float):
    """Decode the layer's tile at the exact point, like the client shader (bilinear, no-data
    aware, directions via vectors). Returns {channel name: value} or None."""
    lay = manifest["layers"].get(layer)
    if not lay:
        return None
    seg = next((g for g in lay["segments"] if t in g["times"]), None)
    if seg is None:
        return None
    z = seg["maxzoom"]
    mx, my = mercator.lonlat_to_mercator01(lon, lat)
    fx, fy = float(mx) * 2**z, float(my) * 2**z
    tx, ty = int(fx), int(fy)
    url = seg["tiles"].replace("{time}", _time_key(t)).replace("{z}", str(z))
    path = out_dir / url.replace("{x}", str(tx)).replace("{y}", str(ty))
    if not path.exists():
        return None
    rgb = read_png(path.read_bytes()).astype(float)
    px = (fx - tx) * mercator.TILE_SIZE + mercator.BUFFER - 0.5
    py = (fy - ty) * mercator.TILE_SIZE + mercator.BUFFER - 0.5
    x0, y0 = int(math.floor(px)), int(math.floor(py))
    wx, wy = px - x0, py - y0
    chans = seg["channels"]
    dch = seg["direction_channel"]
    conv_to = 0.0 if lay["direction_convention"] == "to" else 180.0
    acc = np.zeros(len(chans))
    vec = np.zeros(2)
    wsum = 0.0
    for dy in (0, 1):
        for dx in (0, 1):
            code = rgb[y0 + dy, x0 + dx]
            if (code == 255).any():
                continue
            w = (wx if dx else 1 - wx) * (wy if dy else 1 - wy)
            vals = np.array([c["offset"] + c["scale"] * code[i] for i, c in enumerate(chans)])
            acc += w * vals
            rad = math.radians(vals[dch] + conv_to)
            vec += w * np.array([math.sin(rad), math.cos(rad)]) * max(vals[0], 1e-6)
            wsum += w
    if wsum < 0.5:
        return None
    out = {c["name"]: acc[i] / wsum for i, c in enumerate(chans)}
    u, v = vec / wsum  # motion (towards) vector
    going_to = float(to_direction(np.array(u), np.array(v)))
    out[chans[dch]["name"]] = going_to if conv_to == 0 else (going_to + 180.0) % 360.0
    return out


def _segment_source(manifest: dict, var: str, t: str) -> str:
    for v in manifest["series"]["variables"]:
        if v["name"] == var:
            for seg in v["segments"]:
                if seg["start"] <= t <= seg["end"]:
                    return seg["source"]
    return "?"


def _circ(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


def run_crosscheck(settings: Settings, report: Path) -> int:
    out_dir = settings.output_dir
    manifest = json.loads((out_dir / "manifest.json").read_text())
    times = manifest["series"]["times"]
    tindex = {t: i for i, t in enumerate(times)}
    cache = settings.cache_dir / "api"
    pairs: list[Pair] = []
    tile_pairs: list[Pair] = []
    met_points = {}
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    wanted = {(now.timestamp() + h * 3600) for h in LEADS_H}
    with HttpClient(settings.user_agent, concurrency=1) as http:
        for name, lat, lon in POINTS:
            ours = _series_at(manifest, out_dir, lat, lon)
            if ours is None:
                log("crosscheck.skip", point=name, reason="no series chunk")
                continue
            loc = _get_json(http, f"{LOCATION}?lat={lat:.4f}&lon={lon:.4f}", cache)
            ocean = _get_json(http, f"{OCEAN}?lat={lat:.4f}&lon={lon:.4f}", cache)
            met_points[name] = {
                "requested": [lat, lon],
                "ocean_point": ocean.get("geometry", {}).get("coordinates"),
                "location_updated": loc["properties"]["meta"]["updated_at"],
                "ocean_updated": ocean["properties"]["meta"]["updated_at"],
            }
            for kind, doc in (("loc", loc), ("ocean", ocean)):
                for ts in doc["properties"]["timeseries"]:
                    t = ts["time"]
                    tt = datetime.fromisoformat(t.replace("Z", "+00:00")).timestamp()
                    if tt not in wanted or t not in tindex:
                        continue
                    d = ts["data"]["instant"]["details"]
                    i = tindex[t]
                    if kind == "loc":
                        mapping = {
                            "wind_speed": ("wind_speed", 1.0),
                            "wind_gust": ("wind_speed_of_gust", 1.0),
                            "wind_from_direction": ("wind_from_direction", 1.0),
                        }
                    else:
                        mapping = {
                            "wave_height": ("sea_surface_wave_height", 1.0),
                            "wave_from_direction": ("sea_surface_wave_from_direction", 1.0),
                            "current_speed": ("sea_water_speed", KNOTS_PER_MS),
                            "current_to_direction": ("sea_water_to_direction", 1.0),
                            "sea_temperature": ("sea_water_temperature", 1.0),
                        }
                    for ours_name, (met_name, factor) in mapping.items():
                        if met_name not in d or ours_name not in ours:
                            continue
                        val = ours[ours_name][i]
                        if not np.isfinite(val):
                            continue
                        pairs.append(
                            Pair(
                                name,
                                ours_name,
                                t,
                                float(val),
                                d[met_name] * factor,
                                _segment_source(manifest, ours_name, t),
                            )
                        )
                    # Same comparison from the tiles at the exact MET point (pipeline accuracy).
                    if kind == "loc":
                        tile = _tile_at(manifest, out_dir, "wind", t, lat, lon)
                    else:
                        op = ocean.get("geometry", {}).get("coordinates") or [lon, lat]
                        tile = {}
                        for layer in ("wave_height", "current"):
                            tile.update(_tile_at(manifest, out_dir, layer, t, op[1], op[0]) or {})
                    for ours_name, (met_name, factor) in mapping.items():
                        if tile and ours_name in tile and met_name in d:
                            tile_pairs.append(
                                Pair(
                                    name,
                                    ours_name,
                                    t,
                                    float(tile[ours_name]),
                                    d[met_name] * factor,
                                    _segment_source(manifest, ours_name, t),
                                )
                            )
    text, ok = _report(pairs, tile_pairs, manifest, met_points)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(text)
    log("crosscheck.done", pairs=len(pairs), report=str(report), ok=ok)
    print(text)
    return 0 if ok else 1


# Agreement limits used for the pass/fail line (model differences, not encoding precision).
LIMITS = {
    "wind_speed": ("m/s", 1.5),
    "wind_gust": ("m/s", 3.0),
    "wind_from_direction": ("°", 20.0),
    "wave_height": ("m", 0.5),
    "wave_from_direction": ("°", 25.0),
    "current_speed": ("kn", 0.3),
    "current_to_direction": ("°", 25.0),
    "sea_temperature": ("°C", 0.5),
}
DIRECTION_GATE = {  # skip direction comparisons where the magnitude is too small to define it
    "wind_from_direction": ("wind_speed", 3.0),
    "wave_from_direction": ("wave_height", 0.5),
    "current_to_direction": ("current_speed", 0.3),
}


def _group(pairs: list[Pair]) -> dict[str, list[Pair]]:
    by_var: dict[str, list[Pair]] = {}
    mags = {(p.point, p.time, p.var): p for p in pairs}
    for p in pairs:
        if p.var in DIRECTION_GATE:
            mvar, gate = DIRECTION_GATE[p.var]
            m = mags.get((p.point, p.time, mvar))
            if m is None or min(m.ours, m.met) < gate:
                continue
        by_var.setdefault(p.var, []).append(p)
    return by_var


def _table(by_var: dict[str, list[Pair]]) -> tuple[list[str], bool]:
    lines = [
        "| variable | unit | n | bias (ours − MET) | mean abs diff | max abs diff | limit | ok |",
        "|---|---|---:|---:|---:|---:|---:|:--:|",
    ]
    all_ok = True
    for var, (unit, limit) in LIMITS.items():
        ps = by_var.get(var, [])
        if not ps:
            lines.append(f"| {var} | {unit} | 0 | – | – | – | {limit} | – |")
            continue
        diffs = np.array(
            [_circ(p.ours, p.met) if "direction" in var else p.ours - p.met for p in ps]
        )
        mad = float(np.mean(np.abs(diffs)))
        ok = mad <= limit
        all_ok &= ok
        lines.append(
            f"| {var} | {unit} | {len(ps)} | {np.mean(diffs):+.2f} | {mad:.2f} | "
            f"{np.max(np.abs(diffs)):.2f} | {limit} | {'yes' if ok else 'NO'} |"
        )
    return lines, all_ok


def _report(
    pairs: list[Pair], tile_pairs: list[Pair], manifest: dict, met_points: dict
) -> tuple[str, bool]:
    by_var = _group(pairs)
    lines = [
        "# MET cross-check",
        "",
        f"Generated {datetime.now(UTC).strftime('%Y-%m-%d %H:%M')} UTC by "
        "`weather-layers crosscheck`.",
        "MET values come from api.met.no `locationforecast/2.0/complete` and "
        "`oceanforecast/2.0/complete` at 8 coastal points (4-decimal coordinates), at leads "
        f"{', '.join(str(h) for h in LEADS_H)} h from now. Ours are decoded from the published "
        "files (8-bit encoded), in two ways: A from the tiles, B from the click series.",
        "",
        "Published runs: "
        + ", ".join(f"{s['label']} {s.get('run_id', '?')}" for s in manifest["sources"].values()),
        "",
        "## A. Tiles at MET's own grid point (pipeline accuracy)",
        "",
        "Decoded from the value tiles at the exact coordinates oceanforecast reports for its "
        "grid point (locationforecast: the requested point), with the client's bilinear rule.",
        "",
    ]
    t_lines, t_ok = _table(_group(tile_pairs))
    lines += t_lines
    lines += [
        "",
        "## B. Click series (what the point panel shows)",
        "",
        "Nearest cell of the 0.025° × 0.05° series lattice (≈ 2.8 × 2.4 km), so strong local "
        "gradients (currents between islands) differ more than in A.",
        "",
    ]
    s_lines, s_ok = _table(by_var)
    lines += s_lines
    all_ok = t_ok and s_ok
    lines += [
        "",
        "Direction rows only use times where both magnitudes exceed: wind 3 m/s, waves 0.5 m, "
        "current 0.3 kn (directions of calm conditions are undefined).",
        "",
        "## Points",
        "",
        "| point | requested lat, lon | oceanforecast grid point | locationforecast updated | "
        "oceanforecast updated |",
        "|---|---|---|---|---|",
    ]
    for name, m in met_points.items():
        op = m["ocean_point"]
        lines.append(
            f"| {name} | {m['requested'][0]:.4f}, {m['requested'][1]:.4f} | "
            f"{op[1]:.4f}, {op[0]:.4f} | {m['location_updated']} | {m['ocean_updated']} |"
            if op
            else f"| {name} | {m['requested']} | – | {m['location_updated']} | – |"
        )
    lines += [
        "",
        "## Per-point detail (first lead only)",
        "",
        "| point | variable | time | source | ours | MET |",
        "|---|---|---|---|---:|---:|",
    ]
    seen = set()
    for p in pairs:
        key = (p.point, p.var)
        if key in seen:
            continue
        seen.add(key)
        lines.append(
            f"| {p.point} | {p.var} | {p.time} | {p.source} | {p.ours:.2f} | {p.met:.2f} |"
        )
    return "\n".join(lines) + "\n", all_ok
