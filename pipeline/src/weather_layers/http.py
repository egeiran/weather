"""Polite HTTP client: identifying User-Agent, capped concurrency, backoff, local raw cache.

All outbound requests of the pipeline go through `HttpClient`. MET Norway's terms ask for an
identifying User-Agent, modest request rates and respect for 429/5xx; we honour `Retry-After`.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import random
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

from .log import COUNTERS, log

RETRY_STATUS = {429, 500, 502, 503, 504}


class HttpError(RuntimeError):
    def __init__(self, url: str, status: int, message: str = "") -> None:
        super().__init__(f"HTTP {status} for {url} {message}".strip())
        self.url = url
        self.status = status


@dataclass
class Response:
    url: str
    status: int
    content: bytes
    headers: dict[str, str]
    from_cache: bool = False

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


class HttpClient:
    def __init__(
        self,
        user_agent: str,
        *,
        concurrency: int = 2,
        timeout_s: float = 120.0,
        max_retries: int = 5,
        cache_dir: Path | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep=time.sleep,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"},
            timeout=httpx.Timeout(timeout_s, connect=30.0),
            follow_redirects=True,
            transport=transport,
        )
        self._sem = threading.BoundedSemaphore(max(1, concurrency))
        self._max_retries = max_retries
        self._cache_dir = cache_dir
        self._sleep = sleep
        self._namespace = ""
        if cache_dir is not None:
            cache_dir.mkdir(parents=True, exist_ok=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- cache -----------------------------------------------------------------------------
    def _cache_paths(self, url: str, headers: dict[str, str] | None) -> tuple[Path, Path] | None:
        if self._cache_dir is None:
            return None
        key = url + "\n" + json.dumps(headers or {}, sort_keys=True)
        if self._namespace:
            key = self._namespace + "\n" + key
        digest = hashlib.sha256(key.encode()).hexdigest()
        base = self._cache_dir / digest[:2] / digest
        return base.with_suffix(".bin"), base.with_suffix(".json")

    def _cache_get(self, url: str, headers: dict[str, str] | None) -> Response | None:
        paths = self._cache_paths(url, headers)
        if paths is None or not paths[0].exists() or not paths[1].exists():
            return None
        meta = json.loads(paths[1].read_text())
        COUNTERS.add(cache_hits=1)
        return Response(url, meta["status"], paths[0].read_bytes(), meta["headers"], True)

    def _cache_put(self, url: str, headers: dict[str, str] | None, resp: Response) -> None:
        paths = self._cache_paths(url, headers)
        if paths is None:
            return
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        tmp = paths[0].with_suffix(".tmp")
        tmp.write_bytes(resp.content)
        tmp.replace(paths[0])
        paths[1].write_text(
            json.dumps({"url": url, "status": resp.status, "headers": resp.headers})
        )

    def namespaced(self, namespace: str) -> HttpClient:
        """A view of this client whose cache keys are prefixed (e.g. with a run id), for
        datasets whose URLs stay the same while their content changes (aggregations)."""
        view = object.__new__(HttpClient)
        view.__dict__.update(self.__dict__)
        view._namespace = namespace
        return view

    # -- requests --------------------------------------------------------------------------
    def get(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        cache: bool = False,
        allow_status: tuple[int, ...] = (200,),
    ) -> Response:
        """GET with retries. `cache=True` stores/reads the raw body in the local cache dir.

        Only immutable resources (data subsets of a fixed model run) should be cached; catalog
        listings used for latest-run discovery must not be.
        """
        if cache:
            hit = self._cache_get(url, headers)
            if hit is not None:
                return hit
        attempt = 0
        while True:
            attempt += 1
            try:
                with self._sem:
                    t0 = time.perf_counter()
                    r = self._client.get(url, headers=headers)
                    body = r.content
                # Count wire bytes when available (compressed), else decoded size.
                wire = r.num_bytes_downloaded or len(body)
                COUNTERS.add(bytes_downloaded=wire, requests=1)
                log(
                    "http.get",
                    url=url,
                    status=r.status_code,
                    bytes=wire,
                    decoded_bytes=len(body),
                    duration_s=round(time.perf_counter() - t0, 3),
                    attempt=attempt,
                )
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                if attempt > self._max_retries:
                    raise HttpError(url, -1, f"{type(exc).__name__}: {exc}") from exc
                self._backoff(url, attempt, None, str(exc))
                continue
            if r.status_code in RETRY_STATUS and attempt <= self._max_retries:
                self._backoff(url, attempt, r.headers.get("Retry-After"), f"HTTP {r.status_code}")
                continue
            if r.status_code not in allow_status:
                raise HttpError(url, r.status_code, body[:200].decode("utf-8", "replace"))
            resp = Response(url, r.status_code, body, dict(r.headers))
            if cache and r.status_code in (200, 206):
                self._cache_put(url, headers, resp)
            return resp

    def _backoff(self, url: str, attempt: int, retry_after: str | None, reason: str) -> None:
        delay = min(120.0, 2.0**attempt) * (0.75 + 0.5 * random.random())
        if retry_after:
            with contextlib.suppress(ValueError):
                delay = max(delay, float(retry_after))
        log(
            "http.retry",
            level="warning",
            url=url,
            attempt=attempt,
            delay_s=round(delay, 1),
            reason=reason,
        )
        self._sleep(delay)
