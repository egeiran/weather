"""Command line interface: `weather-layers run|status|validate|crosscheck`."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

from .config import ALL_SOURCES, Settings


def _settings(args: argparse.Namespace) -> Settings:
    s = Settings.from_env()
    changes = {}
    if getattr(args, "area", None):
        changes["area"] = args.area
    if getattr(args, "sources", None):
        srcs = tuple(x.strip() for x in args.sources.split(",") if x.strip())
        bad = set(srcs) - set(ALL_SOURCES)
        if bad:
            raise SystemExit(f"unknown sources: {sorted(bad)}")
        changes["sources"] = srcs
    if getattr(args, "output", None):
        changes["output_dir"] = Path(args.output)
    return dataclasses.replace(s, **changes)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="weather-layers", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="fetch latest runs, build tiles/series, publish manifest")
    r.add_argument("--area", help="dev | coast | 'w,s,e,n' (default: $WEATHER_LAYERS_AREA)")
    r.add_argument("--sources", help=f"comma list of {','.join(ALL_SOURCES)}")
    r.add_argument("--output", help="output dir (default: $WEATHER_LAYERS_OUTPUT_DIR)")
    r.add_argument("--force", action="store_true", help="rebuild even if already built")
    s = sub.add_parser("status", help="print a summary of the published manifest")
    s.add_argument("--output")
    v = sub.add_parser("validate", help="validate manifest.json against the JSON Schema")
    v.add_argument("--output")
    c = sub.add_parser("crosscheck", help="compare decoded series with api.met.no point APIs")
    c.add_argument("--output")
    c.add_argument("--report", default="docs/crosscheck.md")
    args = p.parse_args(argv)
    settings = _settings(args)

    if args.cmd == "run":
        from .publish import run_pipeline

        run_pipeline(settings, force=args.force)
        return 0
    if args.cmd == "status":
        path = settings.output_dir / "manifest.json"
        if not path.exists():
            print("no manifest", file=sys.stderr)
            return 1
        m = json.loads(path.read_text())
        print(f"generated {m['generated_at']} area {m['area']['name']}")
        for name, src in m["sources"].items():
            print(
                f"  {name:8} {src.get('status', '?'):8} {src.get('run_id', '-'):14} "
                f"{src.get('start', '')} .. {src.get('end', '')}"
            )
        for name, layer in m["layers"].items():
            segs = ", ".join(f"{g['label']} ({g['step_hours']}h)" for g in layer["segments"])
            print(f"  layer {name:12} {layer['start']} .. {layer['end']}  {segs}")
        return 0
    if args.cmd == "validate":
        from .schema import validate_manifest

        validate_manifest(json.loads((settings.output_dir / "manifest.json").read_text()))
        print("manifest OK")
        return 0
    if args.cmd == "crosscheck":
        from .crosscheck import run_crosscheck

        return run_crosscheck(settings, Path(args.report))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
