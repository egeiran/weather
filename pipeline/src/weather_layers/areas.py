"""Named areas (lon/lat bounding boxes)."""

from __future__ import annotations

from .mercator import BBox

AREAS: dict[str, BBox] = {
    # Frøya/Hitra, Mid-Norway: small box for fast iteration.
    "dev": BBox(7.5, 63.2, 10.0, 64.2),
    # Whole Norwegian coast and adjacent sea (MEPS covers all of it; NorKyst and WAM cover the
    # coastal sea; inland Sweden/Finland simply has no ocean data).
    "coast": BBox(4.0, 57.5, 31.5, 71.5),
}


def get(name: str) -> BBox:
    if name in AREAS:
        return AREAS[name]
    parts = name.split(",")
    if len(parts) == 4:  # custom "west,south,east,north"
        w, s, e, n = (float(p) for p in parts)
        return BBox(w, s, e, n)
    raise ValueError(f"unknown area {name!r}; use one of {sorted(AREAS)} or 'w,s,e,n'")
