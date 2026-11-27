"""Minimal OPeNDAP (DAP2) client: DAS/DDS parsing and binary `.dods` decoding.

We implement this ourselves instead of using netCDF-C so that every request goes through our
polite HttpClient (User-Agent, retries, cache, byte accounting) and we only ever request
index-sliced subsets.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import numpy as np

from .http import HttpClient

# DAP2 atomic types -> (numpy big-endian dtype on the wire, numpy native dtype)
_DAP_TYPES: dict[str, tuple[str, str]] = {
    "Byte": (">u1", "u1"),
    "Int16": (">i4", "i2"),  # 16-bit ints are sent as 32-bit XDR ints
    "UInt16": (">u4", "u2"),
    "Int32": (">i4", "i4"),
    "UInt32": (">u4", "u4"),
    "Float32": (">f4", "f4"),
    "Float64": (">f8", "f8"),
}


@dataclass
class Decl:
    dtype: str
    name: str
    shape: tuple[int, ...]


_DECL_RE = re.compile(
    r"^\s*(Byte|Int16|UInt16|Int32|UInt32|Float32|Float64|String|Url)\s+([^\[;]+)(.*);\s*$"
)
_DIM_RE = re.compile(r"\[\s*(?:[^=\]]+=\s*)?(\d+)\s*\]")


def parse_dds(dds: str) -> list[Decl]:
    """Flatten a DDS into leaf declarations in wire order (Grid ARRAY then MAPS)."""
    decls: list[Decl] = []
    for line in dds.splitlines():
        m = _DECL_RE.match(line)
        if not m:
            continue
        dtype, name, rest = m.group(1), m.group(2).strip(), m.group(3)
        shape = tuple(int(d) for d in _DIM_RE.findall(rest))
        decls.append(Decl(dtype, name, shape))
    return decls


_GRID_END_RE = re.compile(r"^\s*\}\s*([^;\s]+)\s*;\s*$")


def grid_names(dds: str) -> set[str]:
    """Names of top-level Grid variables in a DDS (they need `name.name[...]` projections)."""
    names: set[str] = set()
    in_grid = False
    for line in dds.splitlines():
        stripped = line.strip()
        if stripped.startswith("Grid {"):
            in_grid = True
            continue
        if in_grid:
            m = _GRID_END_RE.match(line)
            if m:
                names.add(m.group(1))
                in_grid = False
    return names


def decode_dods(payload: bytes) -> dict[str, np.ndarray]:
    """Decode a `.dods` response into {variable name: array}. Later duplicates get a suffix."""
    marker = b"\nData:\n"
    idx = payload.find(marker)
    if idx < 0:
        text = payload[:500].decode("utf-8", "replace")
        raise ValueError(f"Not a DAP2 data response: {text}")
    dds = payload[:idx].decode("utf-8", "replace")
    data = memoryview(payload)[idx + len(marker) :]
    pos = 0
    out: dict[str, np.ndarray] = {}
    for decl in parse_dds(dds):
        if decl.dtype in ("String", "Url"):
            raise ValueError(f"String variables are not supported ({decl.name})")
        wire, native = _DAP_TYPES[decl.dtype]
        count = int(np.prod(decl.shape)) if decl.shape else 1
        if decl.shape:
            (n1, n2) = np.frombuffer(data[pos : pos + 8], dtype=">u4")
            pos += 8
            if n1 != count or n2 != count:
                raise ValueError(f"Length mismatch for {decl.name}: {n1}/{n2} vs {count}")
        itemsize = np.dtype(wire).itemsize
        nbytes = count * itemsize
        if decl.dtype == "Byte":
            arr = np.frombuffer(data[pos : pos + count], dtype=">u1")
            pos += (count + 3) // 4 * 4  # bytes are padded to 4
        else:
            arr = np.frombuffer(data[pos : pos + nbytes], dtype=wire)
            pos += nbytes
        arr = arr.astype(native).reshape(decl.shape) if decl.shape else arr.astype(native)[0]
        key = decl.name
        while key in out:
            key += "_"
        out[key] = arr
    return out


# --- DAS ---------------------------------------------------------------------------------

_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|[{};,]|[^\s{};,"]+')


def parse_das(das: str) -> dict[str, dict[str, Any]]:
    """Parse a DAS into {variable: {attribute: value}} (nested containers flattened by name)."""
    tokens = _TOKEN_RE.findall(das)
    pos = 0
    result: dict[str, dict[str, Any]] = {}

    def parse_block(container: str | None) -> None:
        nonlocal pos
        attrs: dict[str, Any] = {}
        while pos < len(tokens):
            tok = tokens[pos]
            if tok == "}":
                pos += 1
                if container is not None:
                    result.setdefault(container, {}).update(attrs)
                return
            # either "<type> <name> <values...>;" or "<name> {"
            if pos + 1 < len(tokens) and tokens[pos + 1] == "{":
                pos += 2
                parse_block(tok)
                continue
            atype = tok
            name = tokens[pos + 1]
            pos += 2
            values: list[Any] = []
            while pos < len(tokens) and tokens[pos] != ";":
                v = tokens[pos]
                pos += 1
                if v == ",":
                    continue
                values.append(_convert(atype, v))
            pos += 1  # skip ';'
            attrs[name] = values[0] if len(values) == 1 else values
        if container is not None:
            result.setdefault(container, {}).update(attrs)

    # skip the leading "Attributes {"
    while pos < len(tokens) and tokens[pos] != "{":
        pos += 1
    pos += 1
    parse_block(None)
    return result


def _convert(atype: str, token: str) -> Any:
    if token.startswith('"'):
        return bytes(token[1:-1], "utf-8").decode("unicode_escape")
    if atype in ("Float32", "Float64"):
        try:
            return float(token)
        except ValueError:
            return float("nan")
    if atype in ("Byte", "Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64"):
        return int(token)
    return token


# --- client ------------------------------------------------------------------------------


def hyperslab(*slices: tuple[int, int] | tuple[int, int, int] | int) -> str:
    """Build a DAP constraint like [0:1:10][3][5:20] from (start, stop_inclusive[, stride])."""
    parts = []
    for s in slices:
        if isinstance(s, int):
            parts.append(f"[{s}]")
        elif len(s) == 2:
            parts.append(f"[{s[0]}:{s[1]}]")
        else:
            parts.append(f"[{s[0]}:{s[2]}:{s[1]}]")
    return "".join(parts)


class DapDataset:
    def __init__(self, http: HttpClient, url: str, *, cache: bool = True) -> None:
        self.http = http
        self.url = url
        self.cache = cache
        self._das: dict[str, dict[str, Any]] | None = None
        self._dds: list[Decl] | None = None
        self._grids: set[str] = set()

    @property
    def attributes(self) -> dict[str, dict[str, Any]]:
        if self._das is None:
            self._das = parse_das(self.http.get(self.url + ".das", cache=self.cache).text)
        return self._das

    @property
    def variables(self) -> dict[str, Decl]:
        if self._dds is None:
            text = self.http.get(self.url + ".dds", cache=self.cache).text
            self._dds = parse_dds(text)
            self._grids = grid_names(text)
        # Grid maps repeat coordinate names; keep the first (top-level) declaration.
        out: dict[str, Decl] = {}
        for d in self._dds:
            out.setdefault(d.name, d)
        return out

    @property
    def grids(self) -> set[str]:
        _ = self.variables
        return self._grids

    def fetch(self, constraint: dict[str, str]) -> dict[str, np.ndarray]:
        """Fetch arrays. `constraint` maps variable -> hyperslab string, e.g. {"x": "[0:10]"}.

        For Grid variables we request only the array part (`var.var[...]`) to skip the maps.
        """
        grids = self.grids
        parts = []
        for name, slab in constraint.items():
            parts.append(f"{name}.{name}{slab}" if name in grids else f"{name}{slab}")
        query = quote(",".join(parts), safe=":,._")
        payload = self.http.get(f"{self.url}.dods?{query}", cache=self.cache).content
        arrays = decode_dods(payload)
        # Grid responses name the leaf after the variable; strip any "grid.array" prefix.
        return {k.split(".")[-1]: v for k, v in arrays.items()}

    def unpack(self, name: str, raw: np.ndarray) -> np.ndarray:
        """Apply CF scale_factor/add_offset and turn _FillValue/missing_value into NaN."""
        attrs = self.attributes.get(name, {})
        data = raw.astype(np.float64 if raw.dtype == np.float64 else np.float32)
        for key in ("_FillValue", "missing_value"):
            fill = attrs.get(key)
            if fill is None:
                continue
            fills = fill if isinstance(fill, list) else [fill]
            for f in fills:
                if isinstance(f, float) and np.isnan(f):
                    continue
                if raw.dtype.kind == "f":
                    data[np.isclose(raw, f, rtol=1e-6, atol=0)] = np.nan
                else:
                    data[raw == f] = np.nan
        scale = attrs.get("scale_factor")
        offset = attrs.get("add_offset")
        if scale is not None:
            data = data * np.float32(scale)
        if offset is not None:
            data = data + np.float32(offset)
        # Treat absurd magnitudes (e.g. netCDF default fill 9.97e36) as missing too.
        data[np.abs(data) > 1e30] = np.nan
        return data
