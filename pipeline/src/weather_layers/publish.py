"""Orchestration of a pipeline run: discover -> build (if new) -> series -> manifest -> retention.

Idempotent: a source run whose `runs/<source>/<run_id>/run.json` exists (for the same area) is
not rebuilt; if the set of published runs is unchanged the manifest is not rewritten. With
nothing new, a run costs one catalog request per source.
"""

from __future__ import annotations

import fcntl
import json
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from . import areas
from .build import SeaMask, build_run
from .config import ALL_SOURCES, Settings
from .grids import RegularGrid
from .http import HttpClient
from .log import COUNTERS, log, step
from .manifest import build_manifest
from .series import build_series
from .seriesgrid import SeriesWindow
from .sources import get_source
from .sources.base import Source, iso
from .storage import LocalStorage

MANIFEST = "manifest.json"


def load_run_meta(storage: LocalStorage, source: str, run_id: str) -> dict | None:
    data = storage.read_bytes(f"runs/{source}/{run_id}/run.json")
    return json.loads(data) if data else None


def built_runs(storage: LocalStorage, source: str, area_name: str) -> list[str]:
    """Run ids of complete builds for this area, newest first."""
    out = []
    for run_id in sorted(storage.list_dir(f"runs/{source}"), reverse=True):
        meta = load_run_meta(storage, source, run_id)
        if meta and meta.get("area") == area_name:
            out.append(run_id)
    return out


def current_manifest(storage: LocalStorage) -> dict | None:
    data = storage.read_bytes(MANIFEST)
    return json.loads(data) if data else None


def process_source(
    source: Source, http: HttpClient, settings: Settings, storage: LocalStorage, force: bool
) -> dict:
    area = areas.get(settings.area)
    status: dict = {"checked_at": iso(datetime.now(UTC))}
    try:
        source.configure(settings.area, area)
        with step("discover", source=source.name) as info:

            def is_built(run_id: str) -> bool:
                if force:
                    return False
                meta = load_run_meta(storage, source.name, run_id)
                # Rebuild when the area or the source's configuration changed (e.g. ECMWF
                # 0.25 -> 0.1 deg, or a product added/removed).
                return bool(
                    meta
                    and meta.get("area") == settings.area
                    and meta.get("model", source.model_name) == source.model_name
                    and sorted(meta.get("products", {})) == sorted(source.products)
                )

            run = source.latest_complete_run(http, is_built=is_built)
            info["run"] = run.run_id if run else None
        if run is None:
            status.update(status="missing", message="no complete run found on the server")
            return status
        if is_built(run.run_id):
            log("run.skip", source=source.name, run=run.run_id, reason="already built")
            status.update(status="ok", latest_run=run.run_id)
            return status
        with step("fetch+build", source=source.name, run=run.run_id, area=settings.area):
            subset = source.fetch(http, run, area)
            mask = reference_sea_mask(storage, settings) if source.name == "ecmwf" else None
            build_run(
                source, run, subset, settings.area, area, storage, settings.state_dir, sea_mask=mask
            )
        status.update(status="ok", latest_run=run.run_id, _built=True)
    except Exception as exc:  # keep other sources going; the manifest keeps the old run
        log("source.error", level="error", source=source.name, error=f"{type(exc).__name__}: {exc}")
        status.update(status="error", message=f"{type(exc).__name__}: {exc}"[:300])
    return status


def reference_sea_mask(storage: LocalStorage, settings: Settings) -> SeaMask | None:
    """WW3's land/sea mask from its newest build for this area (coastline for ECMWF waves)."""
    for run_id in built_runs(storage, "wam", settings.area):
        f = settings.state_dir / "wam" / run_id / "seamask.npz"
        if f.exists():
            with np.load(f) as z:
                g = json.loads(str(z["grid"]))
                return SeaMask(RegularGrid(**g), z["sea"].astype(np.float32))
    return None


def apply_retention(
    storage: LocalStorage, settings: Settings, manifest: dict | None, previous: dict | None
) -> None:
    keep_refs: set[tuple[str, str]] = set()
    keep_series: set[str] = set()
    for m in (manifest, previous):
        if not m:
            continue
        for name, src in m.get("sources", {}).items():
            if "run_id" in src:
                keep_refs.add((name, src["run_id"]))
        if m.get("series"):
            keep_series.add(m["series"]["id"])
    for name in storage.list_dir("runs"):
        runs = sorted(storage.list_dir(f"runs/{name}"), reverse=True)
        for run_id in runs[settings.retention :]:
            if (name, run_id) in keep_refs:
                continue
            log("retention.delete", source=name, run=run_id)
            storage.delete_prefix(f"runs/{name}/{run_id}")
            shutil.rmtree(settings.state_dir / name / run_id, ignore_errors=True)
    for sid in storage.list_dir("series"):
        if sid not in keep_series:
            log("retention.delete", series=sid)
            storage.delete_prefix(f"series/{sid}")
    storage.clean_staging()
    for stale in Path(settings.state_dir).glob("*/.staging-*"):
        shutil.rmtree(stale, ignore_errors=True)


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def run_lock(state_dir: Path) -> Iterator[None]:
    """Prevent overlapping scheduled runs (non-blocking; a second run exits immediately)."""
    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_dir / ".lock", "w") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AlreadyRunning("another pipeline run holds the lock") from exc
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def run_pipeline(settings: Settings, force: bool = False) -> dict:
    try:
        with run_lock(Path(settings.state_dir)):
            return _run_pipeline(settings, force)
    except AlreadyRunning:
        log("pipeline.locked", level="warning", reason="previous run still in progress")
        return {}


def _run_pipeline(settings: Settings, force: bool = False) -> dict:
    t0 = time.perf_counter()
    storage = LocalStorage(settings.output_dir)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    area = areas.get(settings.area)
    previous = current_manifest(storage)
    statuses: dict[str, dict] = {}
    built_now: set[str] = set()  # sources (re)built in this run, possibly under the same run id
    cache_dir = settings.cache_dir if settings.cache_enabled else None
    with HttpClient(
        settings.user_agent,
        concurrency=settings.concurrency,
        timeout_s=settings.http_timeout_s,
        max_retries=settings.max_retries,
        cache_dir=cache_dir,
    ) as http:
        pruned = http.prune_cache(settings.cache_max_age_h)
        if pruned:
            log("cache.pruned", files=pruned, max_age_h=settings.cache_max_age_h)
        for name in settings.sources:
            source = get_source(name, cache=settings.cache_enabled)
            statuses[name] = process_source(source, http, settings, storage, force)
            if statuses[name].pop("_built", False):
                built_now.add(name)

    # Publish set: newest complete build per source for this area.
    runs: dict[str, dict] = {}
    # Publish every source that has a build for this area; `sources` only limits what this run
    # fetches (sources not fetched now keep their last status).
    prev_sources_all = (previous or {}).get("sources", {})
    for name in ALL_SOURCES:
        if name not in statuses and name in prev_sources_all:
            keep = {
                k: v
                for k, v in prev_sources_all[name].items()
                if k in ("status", "message", "checked_at", "latest_run")
            }
            statuses[name] = keep
    for name in ALL_SOURCES:
        ids = built_runs(storage, name, settings.area)
        if ids:
            meta = load_run_meta(storage, name, ids[0])
            assert meta
            runs[name] = meta
            st = statuses.get(name, {})
            if st.get("status") == "error":
                st["status"] = "stale"
            elif st.get("status") == "missing":
                # No newer complete run on the server yet (e.g. NorKyst being appended 04:30-06:40
                # UTC): the published run is still the newest one, nothing is wrong.
                st["status"] = "pending"
                st["message"] = f"no newer complete run yet; showing {meta['run_id']}"
    same_area = bool(previous) and previous.get("area", {}).get("name") == settings.area
    prev_sources = (previous or {}).get("sources", {}) if same_area else {}
    prev_set = {n: s.get("run_id") for n, s in prev_sources.items() if "run_id" in s}
    new_set = {n: m["run_id"] for n, m in runs.items()}
    # Republish when the run set changes, when a run was rebuilt under the same id (a changed
    # source configuration), or when a source's health changes (e.g. ok -> stale), so clients
    # can show "source down"; otherwise a run with nothing new is a no-op.
    prev_status = {n: s.get("status") for n, s in prev_sources.items()}
    new_status = {n: statuses.get(n, {}).get("status") for n in runs}
    prev_status = {n: s for n, s in prev_status.items() if n in runs}
    unchanged = prev_set == new_set and prev_status == new_status and not built_now
    if same_area and unchanged and not force:
        storage.clean_staging()
        log(
            "publish.noop",
            runs=new_set,
            duration_s=round(time.perf_counter() - t0, 3),
            **COUNTERS.snapshot(),
        )
        return previous or {}
    window = SeriesWindow.for_area(area)
    series = (
        build_series(runs, settings.area, window, storage, settings.state_dir) if runs else None
    )
    manifest = build_manifest(runs, series, settings.area, area, statuses)
    with step("publish.manifest", runs=new_set):
        storage.write_atomic(MANIFEST, json.dumps(manifest, separators=(",", ":")).encode())
    apply_retention(storage, settings, manifest, previous)
    log(
        "pipeline.done",
        duration_s=round(time.perf_counter() - t0, 3),
        runs=new_set,
        **COUNTERS.snapshot(),
    )
    return manifest
