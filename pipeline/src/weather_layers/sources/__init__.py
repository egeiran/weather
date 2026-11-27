"""Forecast sources."""

from __future__ import annotations

from .base import Source


def get_source(name: str, cache: bool = True) -> Source:
    if name == "meps":
        from .meps import Meps

        return Meps(cache=cache)
    if name == "norkyst":
        from .norkyst import NorKyst

        return NorKyst(cache=cache)
    if name == "wam":
        from .wam import Wam

        return Wam(cache=cache)
    if name == "ecmwf":
        from .ecmwf import Ecmwf

        return Ecmwf(cache=cache)
    raise ValueError(f"unknown source {name!r}")
