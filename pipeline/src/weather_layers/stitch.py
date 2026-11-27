"""Time stitching: which source run serves which valid times, per product.

Rule (shared by tile layers and point series): sources are ordered by priority. The first
available source covers all its valid times; each next source covers only times after the
previous sources' last valid time. Within a source, consecutive times with the same step
length form one segment, so the UI can show where the step changes (1 h -> 3 h -> 6 h).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# Product -> sources in priority order.
PRIORITY: dict[str, tuple[str, ...]] = {
    "wind": ("meps", "ecmwf"),
    "waves": ("wam", "wam3", "ecmwf"),
    "swell": ("wam", "wam3", "ecmwf"),
    "current": ("norkyst",),
}


@dataclass
class Segment:
    product: str
    source: str
    run_id: str
    times: list[datetime]
    step_hours: float | None  # None when the segment holds a single time


def _parse(t: str) -> datetime:
    return datetime.fromisoformat(t.replace("Z", "+00:00"))


def stitch(product: str, runs: dict[str, dict]) -> list[Segment]:
    """`runs` maps source name -> run.json dict (only sources that offer `product`)."""
    segments: list[Segment] = []
    last: datetime | None = None
    for src in PRIORITY.get(product, ()):
        meta = runs.get(src)
        if not meta or product not in meta.get("products", {}):
            continue
        times = [_parse(t) for t in meta["times"]]
        if last is not None:
            times = [t for t in times if t > last]
        if not times:
            continue
        for group in _step_groups(times):
            step = (group[1] - group[0]).total_seconds() / 3600 if len(group) > 1 else None
            segments.append(Segment(product, src, meta["run_id"], group, step))
        last = times[-1]
    # Fill in step_hours for single-time segments from the gap to the previous time.
    for i, seg in enumerate(segments):
        if seg.step_hours is None and i > 0:
            seg.step_hours = (seg.times[0] - segments[i - 1].times[-1]).total_seconds() / 3600
    return segments


def _step_groups(times: list[datetime]) -> list[list[datetime]]:
    """Group consecutive times by constant step. A time belongs to the group of the step
    that *leads to it*, except the very first which joins the following step."""
    if len(times) < 3:
        return [times]
    groups: list[list[datetime]] = [[times[0]]]
    cur_step = times[1] - times[0]
    for prev, t in zip(times, times[1:], strict=False):
        step = t - prev
        if step != cur_step:
            groups.append([])
            cur_step = step
        groups[-1].append(t)
    return [g for g in groups if g]
