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
from dataclasses import asdict, dataclass, field
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
class Aux:
    """A secondary grid (overlay or reference sea mask) sampled at the same pixels."""

    index: int  # which overlay (or 0 for the sea mask)
    k: int  # block-averaging factor for this zoom
    sampler: Sampler


@dataclass
class TileJob:
    z: int
    x: int
    y: int
    k: int
    sampler: Sampler
    overlays: list[Aux] = field(default_factory=list)
    mask: Aux | None = None


@dataclass
class SeaMask:
    """A reference land/sea mask (e.g. WW3's) that another ocean source is clipped to."""

    grid: RegularGrid
    sea: np.ndarray  # float32, 1 = sea, 0 = land


def fill_nearest(arr: np.ndarray, max_cells: float | None = None) -> np.ndarray:
    """Replace NaN cells by the value of the nearest valid cell (extrapolate over land),
    at most `max_cells` cells away (further cells stay NaN)."""
    nan = ~np.isfinite(arr)
    if not nan.any() or nan.all():
        return arr
    from scipy.ndimage import distance_transform_edt

    dist, idx = distance_transform_edt(nan, return_distances=True, return_indices=True)
    out = arr[tuple(idx)]
    if max_cells is not None:
        out = np.where(dist <= max_cells, out, np.nan).astype(arr.dtype)
    return out


def grow_mean(arr: np.ndarray, iterations: int = 1) -> np.ndarray:
    """Extrapolate one ring of cells per iteration with the mean of their valid neighbours
    (smoother than nearest-cell filling, which leaves blocky steps)."""
    from scipy.ndimage import convolve

    out = arr.astype(np.float32).copy()
    kernel = np.ones((3, 3), dtype=np.float32)
    for _ in range(iterations):
        valid = np.isfinite(out)
        if valid.all() or not valid.any():
            break
        num = convolve(np.where(valid, out, 0.0), kernel, mode="nearest")
        cnt = convolve(valid.astype(np.float32), kernel, mode="nearest")
        grow = ~valid & (cnt > 0)
        out[grow] = num[grow] / cnt[grow]
    return out


def open_sea(valid: np.ndarray, min_cells: int = 20) -> np.ndarray:
    """Drop small isolated sea patches (a coarse model's stray cells inside fjords)."""
    from scipy.ndimage import label

    labels, n = label(valid)
    if n == 0:
        return valid
    sizes = np.bincount(labels.ravel())
    keep = sizes >= min_cells
    keep[0] = False
    return keep[labels]


def _overlaps(a: BBox, b: BBox) -> bool:
    return a.west < b.east and a.east > b.west and a.south < b.north and a.north > b.south


def _aux(grid: RegularGrid, z: int, lat_mid: float, lon2, lat2, index: int) -> Aux | None:
    """Sampler for a secondary grid; None when, at this zoom, the grid would average down to
    fewer than 2x2 cells (an overlay is irrelevant at such zooms)."""
    k = zoom_coarsen_factor(grid, z, lat_mid)
    if grid.nx // k < 2 or grid.ny // k < 2:
        return None
    return Aux(index, k, Sampler.build(grid.coarsen(k), lon2, lat2))


def intersect(a: BBox, b: BBox) -> BBox | None:
    w, s, e, n = (
        max(a.west, b.west),
        max(a.south, b.south),
        min(a.east, b.east),
        min(a.north, b.north),
    )
    return BBox(w, s, e, n) if (e > w and n > s) else None


def plan_tiles(
    grid: RegularGrid,
    bbox: BBox,
    zooms: range,
    lat_mid: float,
    area: BBox | None = None,
    overlays: list | None = None,
    sea_mask: SeaMask | None = None,
    detail_zooms: range = range(0),
) -> list[TileJob]:
    """Tile jobs with precomputed samplers. `detail_zooms` (above the base max zoom) only get
    tiles where an overlay grid exists; elsewhere the client over-zooms the base tiles."""
    overlays = overlays or []
    jobs = []
    for z in [*zooms, *detail_zooms]:
        k = zoom_coarsen_factor(grid, z, lat_mid)
        cgrid = grid.coarsen(k)
        if z in detail_zooms:
            tiles = set()
            for ov in overlays:
                if _overlaps(ov.footprint, bbox):
                    x0, x1, y0, y1 = mercator.tile_range(ov.footprint, z)
                    tiles |= {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
            x0, x1, y0, y1 = mercator.tile_range(bbox, z)
            tiles = {(x, y) for x, y in tiles if x0 <= x <= x1 and y0 <= y <= y1}
        else:
            x0, x1, y0, y1 = mercator.tile_range(bbox, z)
            tiles = {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
        for tx, ty in sorted(tiles, key=lambda t: (t[1], t[0])):
            lon, lat = mercator.tile_pixel_lonlat(z, tx, ty)
            lon2, lat2 = np.meshgrid(lon, lat)
            sampler = Sampler.build(cgrid, lon2, lat2)
            # Clip to the area (box and polygon) so every source covers the same shape.
            sampler.inside &= bbox.contains(lon2, lat2)
            if area is not None and area.polygon is not None:
                sampler.inside &= area.contains(lon2, lat2)
            job = TileJob(z, tx, ty, k, sampler)
            tb = mercator.tile_bounds(z, tx, ty)
            for oi, ov in enumerate(overlays):
                if _overlaps(ov.footprint, tb):
                    aux = _aux(ov.grid, z, lat_mid, lon2, lat2, oi)
                    if aux is not None:
                        job.overlays.append(aux)
            if sea_mask is not None:
                job.mask = _aux(sea_mask.grid, z, lat_mid, lon2, lat2, 0)
            jobs.append(job)
    return jobs


FEATHER_NATIVE_CELLS = 6.0  # ~5 km for the 800 m grids


def composite(sampled: dict, auxes: list[Aux], ov_inputs: dict, min_weight: float) -> None:
    """Overlay values replace the base where the overlay has data (all inputs valid). Near the
    overlay grid's outer edge the two are blended over a few cells, so no seam shows where
    the models differ slightly; where the base has no data the overlay is used as is."""
    for aux in auxes:
        by_k = ov_inputs.get(aux.index)
        if not by_k:
            continue
        s2 = {n: aux.sampler.sample(a, min_weight=min_weight) for n, a in by_k[aux.k].items()}
        ok = np.all([np.isfinite(v) for v in s2.values()], axis=0)
        if not ok.any():
            continue
        feather = max(1.0, FEATHER_NATIVE_CELLS / aux.k)
        w = np.clip(aux.sampler.edge / feather, 0.0, 1.0) if aux.sampler.edge is not None else 1.0
        base_ok = np.all([np.isfinite(sampled[n]) for n in s2], axis=0)
        w = np.where(base_ok, w, 1.0)
        for n, v in s2.items():
            blended = np.where(base_ok, sampled[n] * (1.0 - w), 0.0) + np.nan_to_num(v) * w
            sampled[n] = np.where(ok, blended, sampled[n])
        if "__valid" in sampled:
            sampled["__valid"] = np.where(ok, 1.0, sampled["__valid"])


def apply_sea_mask(sampled: dict, aux: Aux | None, mask_by_k: dict) -> None:
    """Clip extrapolated ocean values to the reference coastline (own mask outside it)."""
    if "__valid" not in sampled:
        return
    valid = sampled.pop("__valid") >= 0.5
    if aux is not None:
        with np.errstate(invalid="ignore"):
            ref = aux.sampler.sample(mask_by_k[aux.k], min_weight=0.5) >= 0.5
        valid = np.where(aux.sampler.inside, ref, valid)
    for n in sampled:
        sampled[n] = np.where(valid, sampled[n], np.nan)


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
    sea_mask: SeaMask | None = None,
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
    overlays = list(subset.overlays)
    detail = range(zooms.stop, (subset.detail_max_zoom or 0) + 1) if overlays else range(0)
    all_zooms = range(zooms.start, max(zooms.stop, detail.stop))
    with step("plan", source=source.name, run=run.run_id) as info:
        jobs = plan_tiles(grid, domain, zooms, lat_mid, area, overlays, sea_mask, detail)
        info["tiles_per_step_per_product"] = len(jobs)
        info["zooms"] = [all_zooms.start, all_zooms.stop - 1]
        info["coarsen"] = sorted({(j.z, j.k) for j in jobs})
        info["overlays"] = [o.name for o in overlays]
    overlay_ks = {
        i: sorted({a.k for j in jobs for a in j.overlays if a.index == i})
        for i in range(len(overlays))
    }
    mask_by_k = {}
    if sea_mask is not None:
        mask_by_k = {
            k: coarsen_field(sea_mask.sea, k, min_valid_fraction=0.0)
            for k in sorted({j.mask.k for j in jobs if j.mask})
        }

    window = SeriesWindow.for_area(area)
    slon, slat = window.lonlat()
    series_sampler = Sampler.build(grid, slon, slat)
    series_sampler.inside &= area.contains(slon, slat)
    series_ov = [Aux(i, 1, Sampler.build(o.grid, slon, slat)) for i, o in enumerate(overlays)]
    series_mask = Aux(0, 1, Sampler.build(sea_mask.grid, slon, slat)) if sea_mask else None
    if series_mask is not None:
        mask_by_k.setdefault(1, sea_mask.sea)
    sea_seen: np.ndarray | None = None
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

    def write_tile(prefix: str, job: TileJob, product: Product, inputs_by_k, tkey: str, ov_in):
        sampled = {n: job.sampler.sample(a) for n, a in inputs_by_k[job.k].items()}
        composite(sampled, job.overlays, ov_in, 0.5)
        apply_sea_mask(sampled, job.mask, mask_by_k)
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
                if product.ocean and sea_seen is None:
                    # Static land/sea mask of this ocean model, kept for other sources.
                    sea_seen = np.all([np.isfinite(a) for a in inputs.values()], axis=0)
                if product.ocean and sea_mask is not None:
                    # Coarse model (ECMWF): keep only its connected open sea (no stray fjord
                    # cells), extrapolate one ring of cells over its blocky land mask, then
                    # clip to the reference coastline (WW3) after sampling.
                    valid = np.all([np.isfinite(a) for a in inputs.values()], axis=0)
                    sea = open_sea(valid)
                    inputs = {n: grow_mean(np.where(sea, a, np.nan), 1) for n, a in inputs.items()}
                    inputs["__valid"] = sea.astype(np.float32)
                inputs_by_k = {
                    k: {n: coarsen_field(a, k) for n, a in inputs.items()}
                    for k in sorted({j.k for j in jobs})
                }
                ov_in: dict[int, dict] = {}
                for oi, ov in enumerate(overlays):
                    if pname not in ov.products:
                        continue
                    of = ov.fields(subset.times, t_index)
                    if of is None:
                        continue
                    oin = product.inputs(of)
                    ov_in[oi] = {
                        k: {n: coarsen_field(a, k) for n, a in oin.items()}
                        for k in set(overlay_ks[oi]) | {1}
                    }
                todo = jobs
                if pname in available:
                    todo = [j for j in jobs if (j.z, j.x, j.y) in available[pname]]
                results = list(
                    pool.map(
                        lambda j, p=product, ik=inputs_by_k, tk=tkey, oi=ov_in: write_tile(
                            staging, j, p, ik, tk, oi
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
                composite(sampled, series_ov, ov_in, min_w)
                apply_sea_mask(sampled, series_mask, mask_by_k)
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
        for z in all_zooms:
            x0, x1, y0, y1 = mercator.tile_range(domain, z)
            present = [(x, y) for (zz, x, y) in available.get(pname, set()) if zz == z]
            avail[str(z)] = encode_bits(x0, y0, x1, y1, present)
        products_meta[pname] = {
            "channels": [c.to_manifest() for c in product.channels],
            "minzoom": all_zooms.start,
            "maxzoom": all_zooms.stop - 1,
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
        "notes": {**subset.notes, "overlays": [{"name": o.name, "run": o.run} for o in overlays]},
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
    if sea_seen is not None:
        np.savez_compressed(
            state_stage / "seamask.npz",
            sea=sea_seen.astype(np.uint8),
            grid=json.dumps(asdict(grid)),
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
