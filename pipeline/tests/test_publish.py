import dataclasses
import json
from pathlib import Path

import numpy as np
import pytest

from weather_layers import publish
from weather_layers.config import Settings
from weather_layers.encoding import read_png
from weather_layers.schema import validate_manifest
from weather_layers.series import decode_chunk

from .fakes import FakeMeps, FakeNorKyst, t


@pytest.fixture
def env(tmp_path, monkeypatch):
    sources = {"meps": FakeMeps([t(27, 6)]), "norkyst": FakeNorKyst([t(27, 0)])}
    monkeypatch.setattr(publish, "get_source", lambda name, cache=True: sources[name])
    settings = Settings(
        output_dir=tmp_path / "out",
        state_dir=tmp_path / "state",
        cache_dir=tmp_path / "cache",
        use_cache=False,
        area="dev",
        retention=2,
        sources=("meps", "norkyst"),
    )
    return settings, sources


def files(root: Path) -> set[str]:
    return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}


def test_end_to_end_outputs_validate(env):
    settings, _ = env
    m = publish.run_pipeline(settings)
    validate_manifest(m)
    out = settings.output_dir
    assert json.loads((out / "manifest.json").read_text()) == m
    seg = m["layers"]["wind"]["segments"][0]
    assert seg["label"] == "MEPS 06Z" and seg["step_hours"] == 1.0
    # a tile exists, is 258x258 RGB, and decodes to the synthetic wind (5 m/s from the west)
    tile = next((out / "runs/meps/20261127T06Z/wind/20261127T0600Z").rglob("*.png"))
    rgb = read_png(tile.read_bytes())
    assert rgb.shape == (258, 258, 3)
    valid = rgb[..., 0] != 255
    assert valid.any()
    assert np.allclose(rgb[..., 0][valid] * 0.2, 5.0, atol=0.1)
    assert np.allclose(rgb[..., 1][valid] * (360 / 255), 270.0, atol=1.0)
    # ocean layer: land half is no data and current direction is "to" east (90)
    cur = m["layers"]["current"]
    assert cur["direction_convention"] == "to"
    ctile = next((out / "runs/norkyst/20261127T00Z/current").rglob("*.png"))
    c = read_png(ctile.read_bytes())
    sea = c[..., 0] != 255
    assert sea.any() and (~sea).any()
    assert np.allclose(c[..., 1][sea] * (360 / 255), 90.0, atol=1.0)
    # series: one chunk decodes, wind values over time increase 5,6,7,8 m/s
    s = m["series"]
    names = [v["name"] for v in s["variables"]]
    chunk = next((out / s["template"].split("/{cy}")[0]).rglob("*.bin"))
    arr = decode_chunk(chunk.read_bytes())
    ws = arr[names.index("wind_speed")]
    wind_t = [i for i, ti in enumerate(s["times"]) if ti >= "2026-11-27T06:00:00Z"][:4]
    vals = ws[..., wind_t].reshape(-1, 4)
    vals = vals[(vals != 255).all(axis=1)]
    assert np.allclose(vals[0] * 0.2, [5, 6, 7, 8], atol=0.1)


def test_second_run_is_noop(env):
    settings, sources = env
    publish.run_pipeline(settings)
    before = files(settings.output_dir)
    mtime = (settings.output_dir / "manifest.json").stat().st_mtime_ns
    publish.run_pipeline(settings)
    assert files(settings.output_dir) == before
    assert (settings.output_dir / "manifest.json").stat().st_mtime_ns == mtime
    assert sources["meps"].fetches == 1


def test_new_run_publishes_and_retention_keeps_n(env):
    settings, sources = env
    meps = sources["meps"]
    for hour in (6, 9, 12, 15):
        meps.runs.append(t(27, hour))
        m = publish.run_pipeline(settings)
        assert m["sources"]["meps"]["run_id"] == f"20261127T{hour:02d}Z"
    runs = sorted(p.name for p in (settings.output_dir / "runs/meps").iterdir())
    assert runs == ["20261127T12Z", "20261127T15Z"]
    states = sorted(p.name for p in (settings.state_dir / "meps").iterdir())
    assert states == ["20261127T12Z", "20261127T15Z"]
    # only the current and the previous series are kept
    assert len(list((settings.output_dir / "series").iterdir())) == 2


def test_failing_source_keeps_previous_run_and_no_partial_output(env):
    settings, sources = env
    publish.run_pipeline(settings)
    meps = sources["meps"]
    meps.runs.append(t(27, 9))
    meps.fail = True
    m = publish.run_pipeline(settings)
    assert m == {} or m["sources"]["meps"]["run_id"] == "20261127T06Z"
    manifest = json.loads((settings.output_dir / "manifest.json").read_text())
    assert manifest["sources"]["meps"]["run_id"] == "20261127T06Z"
    assert not (settings.output_dir / "runs/meps/20261127T09Z").exists()
    assert not any(".staging" in f for f in files(settings.output_dir))


def test_crash_mid_build_leaves_only_staging_which_is_cleaned(env, monkeypatch):
    settings, sources = env
    publish.run_pipeline(settings)
    meps = sources["meps"]
    meps.runs.append(t(27, 9))
    original = meps.fetch

    def exploding_fetch(http, run, area):
        sub = original(http, run, area)

        def steps():
            for i, f in sub.steps:
                if i == 2:
                    raise RuntimeError("killed mid-run")
                yield i, f

        return dataclasses.replace(sub, steps=steps())

    meps.fetch = exploding_fetch
    publish.run_pipeline(settings)
    manifest = json.loads((settings.output_dir / "manifest.json").read_text())
    assert manifest["sources"]["meps"]["run_id"] == "20261127T06Z"
    assert manifest["sources"]["meps"]["status"] == "stale"
    # the half-written staging dir is removed by retention/cleanup
    assert not any(".staging" in f for f in files(settings.output_dir))
    assert not (settings.output_dir / "runs/meps/20261127T09Z").exists()
