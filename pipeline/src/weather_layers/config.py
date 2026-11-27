"""Configuration from environment variables (all optional, sensible defaults)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__

DEFAULT_USER_AGENT = f"weather-layers/{__version__} (+https://github.com/egeiran/weather)"
ALL_SOURCES = ("meps", "wam", "norkyst", "wam3", "ecmwf")


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _tristate(value: str) -> bool | None:
    v = value.strip().lower()
    if v in ("auto", ""):
        return None
    return v not in ("0", "false", "no", "off")


@dataclass(frozen=True)
class Settings:
    output_dir: Path = Path("data/out")
    state_dir: Path = Path("data/state")
    cache_dir: Path = Path("data/cache")
    use_cache: bool | None = None  # None = auto: on for the dev area only
    cache_max_age_h: float = 48.0
    user_agent: str = DEFAULT_USER_AGENT
    area: str = "dev"
    retention: int = 2
    concurrency: int = 2
    sources: tuple[str, ...] = ALL_SOURCES
    http_timeout_s: float = 120.0
    max_retries: int = 5
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def cache_enabled(self) -> bool:
        """Raw download cache: on by default only for the development area."""
        return self.use_cache if self.use_cache is not None else self.area == "dev"

    @classmethod
    def from_env(cls) -> Settings:
        sources = tuple(
            s.strip()
            for s in _env("WEATHER_LAYERS_SOURCES", ",".join(ALL_SOURCES)).split(",")
            if s.strip()
        )
        unknown = set(sources) - set(ALL_SOURCES)
        if unknown:
            raise ValueError(f"Unknown sources in WEATHER_LAYERS_SOURCES: {sorted(unknown)}")
        return cls(
            output_dir=Path(_env("WEATHER_LAYERS_OUTPUT_DIR", "data/out")),
            state_dir=Path(_env("WEATHER_LAYERS_STATE_DIR", "data/state")),
            cache_dir=Path(_env("WEATHER_LAYERS_CACHE_DIR", "data/cache")),
            use_cache=_tristate(_env("WEATHER_LAYERS_CACHE", "auto")),
            cache_max_age_h=float(_env("WEATHER_LAYERS_CACHE_MAX_AGE_H", "48")),
            user_agent=_env("WEATHER_LAYERS_USER_AGENT", DEFAULT_USER_AGENT),
            area=_env("WEATHER_LAYERS_AREA", "dev"),
            retention=max(1, int(_env("WEATHER_LAYERS_RETENTION", "2"))),
            concurrency=max(1, int(_env("WEATHER_LAYERS_CONCURRENCY", "2"))),
            sources=sources,
            http_timeout_s=float(_env("WEATHER_LAYERS_HTTP_TIMEOUT", "120")),
            max_retries=int(_env("WEATHER_LAYERS_MAX_RETRIES", "5")),
        )
