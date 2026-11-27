"""Structured (JSON lines) logging with per-step timing and byte counters."""

from __future__ import annotations

import json
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class Counters:
    bytes_downloaded: int = 0
    bytes_written: int = 0
    files_written: int = 0
    requests: int = 0
    cache_hits: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, **kwargs: int) -> None:
        with self.lock:
            for key, value in kwargs.items():
                setattr(self, key, getattr(self, key) + value)

    def snapshot(self) -> dict[str, int]:
        with self.lock:
            return {
                "bytes_downloaded": self.bytes_downloaded,
                "bytes_written": self.bytes_written,
                "files_written": self.files_written,
                "requests": self.requests,
                "cache_hits": self.cache_hits,
            }


COUNTERS = Counters()
_stream = sys.stderr
_lock = threading.Lock()


def set_stream(stream: Any) -> None:
    global _stream
    _stream = stream


def log(event: str, level: str = "info", **fields: Any) -> None:
    record = {
        "ts": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "level": level,
        "event": event,
        **fields,
    }
    line = json.dumps(record, default=str, ensure_ascii=False)
    with _lock:
        print(line, file=_stream, flush=True)


@contextmanager
def step(name: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """Time a pipeline step; logs start/end with duration and byte deltas.

    The yielded dict can be filled with extra fields to include in the end record.
    """
    before = COUNTERS.snapshot()
    start = time.perf_counter()
    extra: dict[str, Any] = {}
    log("step.start", step=name, **fields)
    try:
        yield extra
    except Exception as exc:
        log(
            "step.error",
            level="error",
            step=name,
            duration_s=round(time.perf_counter() - start, 3),
            error=f"{type(exc).__name__}: {exc}",
            **fields,
        )
        raise
    after = COUNTERS.snapshot()
    deltas = {k: after[k] - before[k] for k in after}
    log(
        "step.end",
        step=name,
        duration_s=round(time.perf_counter() - start, 3),
        **deltas,
        **fields,
        **extra,
    )
