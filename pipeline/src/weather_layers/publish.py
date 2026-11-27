"""Orchestration of a pipeline run: discover -> build (if new) -> series -> manifest -> retention.

Idempotent: a source run whose `runs/<source>/<run_id>/run.json` exists (for the same area) is
not rebuilt; if the set of published runs is unchanged the manifest is not rewritten. With
nothing new, a run costs one catalog request per source.
"""

from __future__ import annotations

import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from . import areas
from .build import build_run
from .config import Settings
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
                return bool(meta and meta.get("area") == settings.area)

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
            build_run(source, run, subset, settings.area, area, storage, settings.state_dir)
        status.update(status="ok", latest_run=run.run_id)
    except Exception as exc:  # keep other sources going; the manifest keeps the old run
        log("source.error", level="error", source=source.name, error=f"{type(exc).__name__}: {exc}")
        status.update(status="error", message=f"{type(exc).__name__}: {exc}"[:300])
    return status


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


def run_pipeline(settings: Settings, force: bool = False) -> dict:
    t0 = time.perf_counter()
    storage = LocalStorage(settings.output_dir)
    settings.state_dir.mkdir(parents=True, exist_ok=True)
    area = areas.get(settings.area)
    previous = current_manifest(storage)
    statuses: dict[str, dict] = {}
    cache_dir = settings.cache_dir if settings.use_cache else None
    with HttpClient(
        settings.user_agent,
        concurrency=settings.concurrency,
        timeout_s=settings.http_timeout_s,
        max_retries=settings.max_retries,
        cache_dir=cache_dir,
    ) as http:
        for name in settings.sources:
            source = get_source(name, cache=settings.use_cache)
            statuses[name] = process_source(source, http, settings, storage, force)

    # Publish set: newest complete build per source for this area.
    runs: dict[str, dict] = {}
    for name in settings.sources:
        ids = built_runs(storage, name, settings.area)
        if ids:
            meta = load_run_meta(storage, name, ids[0])
            assert meta
            runs[name] = meta
            st = statuses.get(name, {})
            if st.get("status") == "error":
                st["status"] = "stale"
    prev_set = (
        {
            n: s.get("run_id")
            for n, s in (previous or {}).get("sources", {}).items()
            if "run_id" in s
        }
        if previous and previous.get("area", {}).get("name") == settings.area
        else None
    )
    new_set = {n: m["run_id"] for n, m in runs.items()}
    if prev_set == new_set and not force:
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
