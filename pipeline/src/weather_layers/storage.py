"""Storage behind a small interface. Only the local filesystem is implemented.

Keys are '/'-separated relative paths. Publishing protocol (see docs/architecture.md):
1. A run is written under a staging prefix, then `promote()`d to its final prefix.
   Final prefixes are unique per model run and immutable once promoted.
2. `manifest.json` is written last with `write_atomic()`. Readers only discover runs through
   the manifest, so they never see a half-written run.
A blob-store implementation can make `promote()` a no-op (write directly to the final,
not-yet-referenced prefix) because the manifest-last rule already gives atomicity.
"""

from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Protocol

from .log import COUNTERS


class Storage(Protocol):
    def write_bytes(self, key: str, data: bytes) -> None: ...
    def write_atomic(self, key: str, data: bytes) -> None: ...
    def read_bytes(self, key: str) -> bytes | None: ...
    def exists(self, key: str) -> bool: ...
    def list_dir(self, prefix: str) -> list[str]: ...
    def delete_prefix(self, prefix: str) -> None: ...
    def staging_prefix(self, final_prefix: str) -> str: ...
    def promote(self, staging: str, final: str) -> None: ...
    def size_of_prefix(self, prefix: str) -> tuple[int, int]: ...


class LocalStorage:
    STAGING_MARK = ".staging-"

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise ValueError(f"key escapes storage root: {key}")
        return p

    def write_bytes(self, key: str, data: bytes) -> None:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        COUNTERS.add(bytes_written=len(data), files_written=1)

    def write_atomic(self, key: str, data: bytes) -> None:
        p = self.path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.name}.{uuid.uuid4().hex}.tmp")
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, p)
        COUNTERS.add(bytes_written=len(data), files_written=1)

    def read_bytes(self, key: str) -> bytes | None:
        p = self.path(key)
        return p.read_bytes() if p.is_file() else None

    def exists(self, key: str) -> bool:
        return self.path(key).exists()

    def list_dir(self, prefix: str) -> list[str]:
        p = self.path(prefix)
        if not p.is_dir():
            return []
        return sorted(c.name for c in p.iterdir() if not c.name.startswith("."))

    def delete_prefix(self, prefix: str) -> None:
        p = self.path(prefix)
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()

    def staging_prefix(self, final_prefix: str) -> str:
        parent, _, name = final_prefix.rstrip("/").rpartition("/")
        stage = f"{self.STAGING_MARK}{name}-{uuid.uuid4().hex[:8]}"
        return f"{parent}/{stage}" if parent else stage

    def promote(self, staging: str, final: str) -> None:
        src, dst = self.path(staging), self.path(final)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        os.replace(src, dst)  # atomic rename on the same filesystem

    def clean_staging(self, prefix: str = "") -> int:
        """Remove leftovers of crashed runs (directories starting with .staging-)."""
        removed = 0
        base = self.path(prefix) if prefix else self.root
        for p in base.rglob(f"{self.STAGING_MARK}*"):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                removed += 1
        return removed

    def size_of_prefix(self, prefix: str) -> tuple[int, int]:
        """(bytes, file count) under prefix."""
        p = self.path(prefix)
        total = files = 0
        if p.is_file():
            return p.stat().st_size, 1
        for f in p.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
                files += 1
        return total, files
