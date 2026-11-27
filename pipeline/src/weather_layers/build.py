"""Build one source run: regrid every step into value tiles + point-series state.

Output (public, under `runs/<source>/<run_id>/`):
    run.json                                       metadata used to assemble the manifest
    <product>/<YYYYMMDDTHHMMZ>/<z>/<x>/<y>.png     258x258 RGB value tiles
State (private, under `<state_dir>/<source>/<run_id>/`):
    <product>.npy   uint8 codes [T, 3, rows, cols] on the series lattice window of the area
    series.json     window + times
"""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import encoding as enc
from . import mercator
from .availability import encode_bits
from .grids import RegularGrid, Sampler, coarsen_field, zoom_coarsen_factor
from .log import COUNTERS, log, step
from .mercator import BBox
from .products import PRODUCTS, Product
from .seriesgrid import SeriesWindow
from .sources.base import Run, Source, Subset, iso, time_key
from .sources.projected import footprint_bbox
from .storage import LocalStorage

RUN_SCHEMA = "weather-layers/run@1"


@dataclass
class TileJob:
    z: int
    x: int
    y: int
    k: int
    sampler: Sampler


def intersect(a: BBox, b: BBox) -> BBox | None:
    w, s, e, n = (
        max(a.west, b.west),
        max(a.south, b.south),
        min(a.east, b.east),
        min(a.north, b.north),
    )
    return BBox(w, s, e, n) if (e > w and n > s) else None


def plan_tiles(grid: RegularGrid, bbox: BBox, zooms: range, lat_mid: float) -> list[TileJob]:
    jobs = []
    for z in zooms:
        k = zoom_coarsen_factor(grid, z, lat_mid)
        cgrid = grid.coarsen(k)
        x0, x1, y0, y1 = mercator.tile_range(bbox, z)
        for ty in range(y0, y1 + 1):
            for tx in range(x0, x1 + 1):
                lon, lat = mercator.tile_pixel_lonlat(z, tx, ty)
                lon2, lat2 = np.meshgrid(lon, lat)
                sampler = Sampler.build(cgrid, lon2, lat2)
                # Clip to the area so every source shows the same lat/lon rectangle.
                sampler.inside &= (
                    (lon2 >= bbox.west)
                    & (lon2 <= bbox.east)
                    & (lat2 >= bbox.south)
                    & (lat2 <= bbox.north)
                )
                jobs.append(TileJob(z, tx, ty, k, sampler))
    return jobs


def encode_tile(product: Product, sampled: dict[str, np.ndarray]) -> np.ndarray:
    outs = product.outputs(sampled)
    return np.stack(
        [enc.encode(o, ch) for o, ch in zip(outs, product.channels, strict=True)], axis=-1
    )


def build_run(
    source: Source,
    run: Run,
    subset: Subset,
    area_name: str,
    area: BBox,
    storage: LocalStorage,
    state_dir: Path,
    workers: int | None = None,
) -> dict:
    final = f"runs/{source.name}/{run.run_id}"
    staging = storage.staging_prefix(final)
    state_final = state_dir / source.name / run.run_id
    state_stage = state_dir / source.name / f".staging-{run.run_id}-{os.getpid()}"
    shutil.rmtree(state_stage, ignore_errors=True)
    state_stage.mkdir(parents=True)

    grid = subset.grid
    domain = intersect(area, footprint_bbox(grid))
    if domain is None:
        raise ValueError(f"{source.name}: area {area_name} outside the model domain")
    lat_mid = (domain.south + domain.north) / 2
    zooms = range(source.min_zoom(), source.max_zoom() + 1)
    with step("plan", source=source.name, run=run.run_id) as info:
        jobs = plan_tiles(grid, domain, zooms, lat_mid)
        info["tiles_per_step_per_product"] = len(jobs)
        info["zooms"] = [zooms.start, zooms.stop - 1]
        info["coarsen"] = sorted({(j.z, j.k) for j in jobs})

    window = SeriesWindow.for_area(area)
    slon, slat = window.lonlat()
    series_sampler = Sampler.build(grid, slon, slat)
    ntimes = len(subset.times)
    series_arrays = {
        p: np.lib.format.open_memmap(
            state_stage / f"{p}.npy",
            mode="w+",
            dtype=np.uint8,
            shape=(ntimes, 3, window.ny, window.nx),
        )
        for p in source.products
    }
    available: dict[str, set[tuple[int, int, int]]] = {}
    pool = ThreadPoolExecutor(max_workers=workers or min(8, os.cpu_count() or 2))
    t_start = time.perf_counter()

    def write_tile(prefix: str, job: TileJob, product: Product, inputs_by_k, tkey: str):
        sampled = {n: job.sampler.sample(a) for n, a in inputs_by_k[job.k].items()}
        rgb = encode_tile(product, sampled)
        if (rgb == enc.NODATA).all():
            return None
        storage.write_bytes(
            f"{prefix}/{product.name}/{tkey}/{job.z}/{job.x}/{job.y}.png", enc.png_bytes(rgb)
        )
        return (job.z, job.x, job.y)

    with step("build", source=source.name, run=run.run_id, steps=ntimes) as info:
        for t_index, fields in subset.steps:
            tkey = time_key(subset.times[t_index])
            for pname in source.products:
                product = PRODUCTS[pname]
                inputs = product.inputs(fields)
                inputs_by_k = {
                    k: {n: coarsen_field(a, k) for n, a in inputs.items()}
                    for k in sorted({j.k for j in jobs})
                }
                todo = jobs
                if pname in available:
                    todo = [j for j in jobs if (j.z, j.x, j.y) in available[pname]]
                results = list(
                    pool.map(
                        lambda j, p=product, ik=inputs_by_k, tk=tkey: write_tile(
                            staging, j, p, ik, tk
                        ),
                        todo,
                    )
                )
                if pname not in available:
                    # Tile availability is fixed by the first step (land masks are static).
                    available[pname] = {r for r in results if r is not None}
                # Point series: nearest-sea borrowing at the coast for ocean products.
                min_w = 1e-3 if product.ocean else 0.5
                sampled = {n: series_sampler.sample(a, min_weight=min_w) for n, a in inputs.items()}
                codes = encode_tile(product, sampled)  # (ny, nx, 3)
                series_arrays[pname][t_index] = np.moveaxis(codes, -1, 0)
            if t_index % 12 == 0:
                log(
                    "build.progress",
                    source=source.name,
                    run=run.run_id,
                    step=t_index,
                    of=ntimes,
                    elapsed_s=round(time.perf_counter() - t_start, 1),
                )
        info["tiles"] = {p: len(v) for p, v in available.items()}
    pool.shutdown()
    for arr in series_arrays.values():
        arr.flush()
    del series_arrays

    products_meta = {}
    for pname in source.products:
        product = PRODUCTS[pname]
        avail = {}
        for z in zooms:
            x0, x1, y0, y1 = mercator.tile_range(domain, z)
            present = [(x, y) for (zz, x, y) in available.get(pname, set()) if zz == z]
            avail[str(z)] = encode_bits(x0, y0, x1, y1, present)
        products_meta[pname] = {
            "channels": [c.to_manifest() for c in product.channels],
            "minzoom": zooms.start,
            "maxzoom": zooms.stop - 1,
            "bounds": [round(v, 5) for v in domain.as_list()],
            "template": f"{final}/{pname}/{{time}}/{{z}}/{{x}}/{{y}}.png",
            "availability": avail,
        }
    meta = {
        "schema": RUN_SCHEMA,
        "source": source.name,
        "run_id": run.run_id,
        "reference_time": iso(run.reference_time),
        "created_at": iso(datetime.now(UTC)),
        "build_id": uuid.uuid4().hex[:12],
        "area": area_name,
        "area_bounds": area.as_list(),
        **source.describe(),
        "times": [iso(t) for t in subset.times],
        "time_format": "%Y%m%dT%H%MZ",
        "products": products_meta,
        "notes": subset.notes,
    }
    (state_stage / "series.json").write_text(
        json.dumps(
            {
                "window": window.to_manifest(),
                "times": meta["times"],
                "products": list(source.products),
            }
        )
    )
    storage.write_bytes(f"{staging}/run.json", json.dumps(meta, indent=1).encode())
    # Promote: state first, then the public run directory (run.json marks completion).
    shutil.rmtree(state_final, ignore_errors=True)
    os.replace(state_stage, state_final)
    storage.promote(staging, final)
    size, files = storage.size_of_prefix(final)
    meta["stats"] = {
        "bytes_on_disk": size,
        "files": files,
        "bytes_written_total": COUNTERS.bytes_written,
    }
    log("run.built", source=source.name, run=run.run_id, bytes_on_disk=size, files=files)
    return meta
