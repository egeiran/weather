"""Manifest JSON Schema validation (schema/manifest.schema.json at the repo root)."""

from __future__ import annotations

import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[3] / "schema" / "manifest.schema.json"


def load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def validate_manifest(manifest: dict) -> None:
    import jsonschema

    jsonschema.validate(manifest, load_schema(), cls=jsonschema.Draft202012Validator)
