"""Assemble manifest.json — the contract between pipeline and client (schema/manifest.schema.json).

Versioning: SCHEMA_VERSION follows semver. Adding optional fields is a minor bump; anything
that changes meaning or removes fields is a major bump (clients check the major version).
"""

from __future__ import annotations

from datetime import UTC, datetime

from . import mercator
from .sources.base import iso
from .stitch import stitch

SCHEMA_VERSION = "1.0.0"

# UI layers: which product/channel is the colour value and which channel gives direction.
LAYERS = {
    "wind": {
        "product": "wind",
        "value": "wind_speed",
        "direction": "wind_from_direction",
        "convention": "from",
        "unit": "m/s",
        "particles": True,
    },
    "gust": {
        "product": "wind",
        "value": "wind_gust",
        "direction": "wind_from_direction",
        "convention": "from",
        "unit": "m/s",
        "particles": True,
    },
    "wave_height": {
        "product": "waves",
        "value": "wave_height",
        "direction": "wave_from_direction",
        "convention": "from",
        "unit": "m",
        "particles": True,
    },
    "wave_period": {
        "product": "waves",
        "value": "wave_period",
        "direction": "wave_from_direction",
        "convention": "from",
        "unit": "s",
        "particles": True,
    },
    "swell": {
        "product": "swell",
        "value": "swell_height",
        "direction": "swell_from_direction",
        "convention": "from",
        "unit": "m",
        "particles": True,
    },
    "current": {
        "product": "current",
        "value": "current_speed",
        "direction": "current_to_direction",
        "convention": "to",
        "unit": "kn",
        "particles": True,
    },
}

MET = {
    "name": "MET Norway",
    "text": "Based on data from MET Norway",
    "url": "https://www.met.no/en/free-meteorological-data/Licensing-and-crediting",
    "license": "NLOD 2.0 / CC BY 4.0",
}
ECMWF = {
    "name": "ECMWF",
    "text": (
        "This service is based on data and products of the European Centre for Medium-Range "
        "Weather Forecasts (ECMWF), modified (regridded and tiled). ECMWF does not accept any "
        "liability whatsoever for any error or omission in the data, their availability, or for "
        "any loss or damage arising from their use."
    ),
    "url": "https://www.ecmwf.int",
    "license": "CC BY 4.0",
}
ATTRIBUTION = {"meps": MET, "wam": MET, "norkyst": MET, "ecmwf": ECMWF}


def build_manifest(
    runs: dict[str, dict],
    series: dict | None,
    area_name: str,
    area: mercator.BBox,
    source_status: dict[str, dict],
) -> dict:
    layers = {}
    for lname, spec in LAYERS.items():
        segs = stitch(spec["product"], runs)
        if not segs:
            continue
        out_segs = []
        for s in segs:
            p = runs[s.source]["products"][spec["product"]]
            channels = [c["name"] for c in p["channels"]]
            out_segs.append(
                {
                    "source": s.source,
                    "run_id": s.run_id,
                    "label": f"{runs[s.source]['label']} {s.run_id[-3:]}",
                    "start": iso(s.times[0]),
                    "end": iso(s.times[-1]),
                    "step_hours": s.step_hours,
                    "times": [iso(t) for t in s.times],
                    "tiles": p["template"],
                    "minzoom": p["minzoom"],
                    "maxzoom": p["maxzoom"],
                    "bounds": p["bounds"],
                    "availability": p["availability"],
                    "channels": p["channels"],
                    "value_channel": channels.index(spec["value"]),
                    "direction_channel": channels.index(spec["direction"]),
                }
            )
        layers[lname] = {
            "product": spec["product"],
            "unit": spec["unit"],
            "value": spec["value"],
            "direction": spec["direction"],
            "direction_convention": spec["convention"],
            "particles": spec["particles"],
            "start": out_segs[0]["start"],
            "end": out_segs[-1]["end"],
            "segments": out_segs,
        }
    sources = {}
    for name, meta in runs.items():
        sources[name] = {
            "label": meta["label"],
            "model": meta["model"],
            "run_id": meta["run_id"],
            "reference_time": meta["reference_time"],
            "attribution": meta["attribution"],
            "license": meta["license"],
            "products": sorted(meta["products"]),
            "start": meta["times"][0],
            "end": meta["times"][-1],
            **source_status.get(name, {"status": "ok"}),
        }
    for name, st in source_status.items():
        sources.setdefault(name, {"label": name.upper(), **st})
    attributions = []
    for name in ("meps", "wam", "norkyst", "ecmwf"):
        a = ATTRIBUTION[name]
        if name in runs and a not in attributions:
            attributions.append(a)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso(datetime.now(UTC)),
        "area": {"name": area_name, "bounds": area.as_list()},
        "tile": {
            "size": mercator.TILE_SIZE,
            "buffer": mercator.BUFFER,
            "format": "png",
            "encoding": "rgb8-linear",
            "nodata": 255,
            "scheme": "xyz",
            "time_format": "%Y%m%dT%H%MZ",
        },
        "attribution": attributions,
        "sources": sources,
        "layers": layers,
        "series": series,
    }
