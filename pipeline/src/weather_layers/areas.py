"""Named areas: lon/lat boxes, optionally narrowed to a polygon."""

from __future__ import annotations

import json
from pathlib import Path

from .mercator import BBox

# Mainland Norway and the sea off it, from the Skagerrak to the Barents Sea. The land side
# follows the borders with Sweden, Finland and Russia with ~15 km to spare; Denmark, the Baltic
# and inland Sweden/Finland are left out. Sea extends ~100-250 km offshore (models' own limits
# apply beyond that). Coarse on purpose: it only decides what to fetch and draw.
NORWAY = (
    (4.0, 57.5),
    (9.6, 57.5),
    (10.1, 57.85),
    (10.9, 57.95),
    (11.1, 58.5),
    (11.45, 59.0),
    (11.95, 59.5),
    (12.1, 59.9),
    (12.75, 60.15),
    (12.95, 60.8),
    (12.7, 61.4),
    (12.5, 62.0),
    (12.45, 62.6),
    (12.4, 63.3),
    (12.55, 63.9),
    (14.25, 64.4),
    (14.25, 65.0),
    (14.8, 65.7),
    (15.9, 66.5),
    (16.6, 67.4),
    (17.6, 67.9),
    (18.5, 68.4),
    (19.3, 68.5),
    (20.4, 69.0),
    (21.1, 68.95),
    (22.6, 68.5),
    (24.0, 68.45),
    (25.3, 68.7),
    (25.9, 69.3),
    (26.9, 69.8),
    (27.7, 70.05),
    (28.1, 69.75),
    (28.6, 69.3),
    (28.7, 68.95),
    (29.4, 69.0),
    (30.2, 69.4),
    (31.2, 69.7),
    (31.5, 69.75),
    (31.5, 71.5),
    (20.0, 71.5),
    (17.0, 71.0),
    (13.0, 69.0),
    (9.5, 67.0),
    (6.0, 64.5),
    (4.0, 62.0),
    (4.0, 57.5),
)


def _from_ring(ring) -> BBox:
    ring = tuple((float(x), float(y)) for x, y in ring)
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return BBox(min(xs), min(ys), max(xs), max(ys), polygon=ring)


AREAS: dict[str, BBox] = {
    # Frøya/Hitra, Mid-Norway: small box for fast iteration.
    "dev": BBox(7.5, 63.2, 10.0, 64.2),
    # Whole Norwegian coast as a plain rectangle (includes much of Sweden and Finland).
    "coast": BBox(4.0, 57.5, 31.5, 71.5),
    # Production: Norway and its sea as a polygon (about half the download of "coast").
    "norway": _from_ring(NORWAY),
}


def get(name: str) -> BBox:
    """Named area, 'w,s,e,n' box, or a GeoJSON file with a Polygon (first ring is used)."""
    if name in AREAS:
        return AREAS[name]
    if name.endswith((".geojson", ".json")) and Path(name).is_file():
        doc = json.loads(Path(name).read_text())
        geom = doc.get("geometry", doc)
        if doc.get("type") == "FeatureCollection":
            geom = doc["features"][0]["geometry"]
        if geom.get("type") != "Polygon":
            raise ValueError("GeoJSON area must be a Polygon")
        return _from_ring(geom["coordinates"][0])
    parts = name.split(",")
    if len(parts) == 4:  # custom "west,south,east,north"
        w, s, e, n = (float(p) for p in parts)
        return BBox(w, s, e, n)
    raise ValueError(f"unknown area {name!r}; use one of {sorted(AREAS)}, 'w,s,e,n' or a .geojson")
