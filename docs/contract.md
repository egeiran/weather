# Contract: files on disk

The pipeline and the client meet only through files under the output directory
(`WEATHER_LAYERS_OUTPUT_DIR`, default `data/out`). A host serves this directory (or a copy of it
in blob storage) as static files behind its own authentication. Everything a client needs is
discovered from `manifest.json`.

```
manifest.json                                          the only mutable file (replaced atomically)
runs/<source>/<run_id>/run.json                        per-run metadata (pipeline-internal, harmless to serve)
runs/<source>/<run_id>/<product>/<time>/<z>/<x>/<y>.png value tiles (immutable)
series/<series_id>/<cy>/<cx>.bin                        point-series chunks (immutable)
series/<series_id>/series.json                          series metadata (pipeline-internal)
```

- `<source>`: `meps`, `wam` (WW3 4 km), `norkyst`, `ecmwf`. `<run_id>`: `YYYYMMDDTHHZ`.
- `<product>`: `wind`, `waves`, `swell`, `current`. `<time>`: valid time `YYYYMMDDTHHMMZ` (UTC).
- Paths under `runs/` and `series/` are **immutable**: a published URL never changes content.
  Serve them with `Cache-Control: private, max-age=31536000, immutable` (`private`: they sit
  behind auth, so shared caches must not keep them); serve `manifest.json`
  with `no-cache` (or a short max-age) so clients see new runs.
- Readers must only follow URLs found in the current manifest. Directories without a manifest
  reference may be half-written (staging) or about to be deleted (retention).

## manifest.json

JSON Schema: [`schema/manifest.schema.json`](../schema/manifest.schema.json) (draft 2020-12).
Validate with `uv run --project pipeline weather-layers validate`.

| field | meaning |
|---|---|
| `schema_version` | semver, currently `1.0.0` |
| `generated_at` | when this manifest was written (UTC) |
| `area` | `{name, bounds:[w,s,e,n], polygon?}` of the pipeline run; with a polygon, data outside it is no-data |
| `tile` | `{size: 256, buffer: 1, format: "png", encoding: "rgb8-linear", nodata: 255, scheme: "xyz", time_format}` |
| `attribution[]` | `{name, text, url, license}` to show in the UI (MET Norway, ECMWF) |
| `sources{}` | per source: `label`, `model`, `run_id`, `reference_time`, `start`, `end`, `status`, `message`, `checked_at`. Status: `ok` newest run published; `pending` no newer complete run on the server yet (previous run shown, normal); `stale` the last fetch failed, previous run shown; `missing`/`error` nothing published for this source |
| `layers{}` | per UI layer (`wind`, `gust`, `wave_height`, `wave_period`, `swell`, `current`), see below |
| `series` | point-series description or `null` |

### Layers and segments

```jsonc
"wave_height": {
  "product": "waves",                  // which tile product holds the data
  "unit": "m",
  "value": "wave_height",              // channel name shown as colour
  "direction": "wave_from_direction",  // channel used for arrows/particles
  "direction_convention": "from",      // "from" (wind, waves) or "to" (currents)
  "particles": true,
  "start": "…", "end": "…",            // first/last valid time over all segments
  "segments": [                        // time-stitched, in order, non-overlapping
    {
      "source": "wam", "run_id": "20261127T06Z", "label": "WW3 06Z",
      "start": "…", "end": "…", "step_hours": 1,
      "times": ["2026-11-27T06:00:00Z", …],   // valid times with tiles
      "tiles": "runs/wam/20261127T06Z/waves/{time}/{z}/{x}/{y}.png",
      "minzoom": 1, "maxzoom": 4,              // tiles exist only in this zoom range; over-zoom above
      "bounds": [w, s, e, n],                  // data rectangle
      "availability": { "5": {x0, y0, width, height, count, bits} , … },
      "channels": [ {name, unit, scale, offset, nodata, min, max, wrap?}, ×3 ],  // R, G, B
      "value_channel": 0, "direction_channel": 2
    },
    { "source": "ecmwf", "label": "ECMWF 00Z", "step_hours": 3, … },
    { "source": "ecmwf", "label": "ECMWF 00Z", "step_hours": 6, … }
  ]
}
```

- **Stitching rule:** sources in priority order (wind: MEPS → ECMWF; waves/swell: WW3 → ECMWF;
  current: NorKyst only). A later source only covers times after the previous source's last time.
  Segments split where the step length changes, so the UI can show 1 h → 3 h → 6 h.
- **Picking a tile:** find the segment containing the wanted time (nearest valid time within half
  a step), `z = clamp(floor(mapZoom), minzoom, maxzoom)`, substitute `{time}` (valid time as
  `YYYYMMDDTHHMMZ`), `{z}`, `{x}`, `{y}`. Skip tiles whose bit is 0 in `availability[z]`.
- **Availability bitset:** base64; bit *i* (LSB first within each byte) is tile
  `(x0 + i mod width, y0 + floor(i / width))`. Missing bits = no tile (e.g. all land).

## Tiles

- 258 × 258 px **RGB PNG** (colour type 2, no alpha, no gAMA/iCCP/sRGB chunks). The inner
  256 × 256 px cover the XYZ tile; a 1-px border holds the neighbours' samples. Image pixel *j*
  (0…257) has its centre at tile-local `u = (j − 0.5) / 256`.
- Each channel: `value = offset + scale × code` for code 0…254; **255 = no data** (land for ocean
  models, outside the area/domain). Channels with `wrap` (directions) are modulo `wrap`.
- Decode without premultiplication or colour conversion (`createImageBitmap(blob,
  {premultiplyAlpha: 'none', colorSpaceConversion: 'none'})`), sample with NEAREST and interpolate
  manually: drop no-data taps, renormalise; a sample is valid when ≥ 50 % of its weight is valid
  (the reference colour field fades out between 40 % and 60 % for a soft coastline).
  Interpolate directions as vectors.

| product | R | G | B |
|---|---|---|---|
| `wind` | `wind_speed` m/s, 0.2 steps (0–50.8) | `wind_from_direction` °, 360/255 | `wind_gust` m/s, 0.25 (0–63.5) |
| `waves` | `wave_height` m, 0.1 (0–25.4) | `wave_period` s (peak), 0.1 (0–25.4) | `wave_from_direction` °, from |
| `swell` | `swell_height` m, 0.1 | `swell_period` s, 0.1 | `swell_from_direction` °, from |
| `current` | `current_speed` kn, 0.04 (0–10.16) | `current_to_direction` °, **to** | `sea_temperature` °C, 0.15 from −3 |

Maximum quantisation error is half a step: wind 0.1 m/s, gust 0.125 m/s, wave height 0.05 m,
period 0.05 s, current 0.02 kn, direction 0.71°, temperature 0.075 °C.

### Direction conventions

- **from** (meteorological, wind and waves): bearing the wind/waves come *from*, clockwise from true north.
- **to** (oceanographic, currents): bearing the water flows *towards*.
- Motion vector for arrows/particles: `(sin θ, cos θ) × speed` with θ = direction + 180° for
  "from" and θ = direction for "to". Arrows point where the flow goes.

## Point series

```jsonc
"series": {
  "id": "4e70f92a91d0",
  "template": "series/4e70f92a91d0/{cy}/{cx}.bin",
  "format": "WLS1+gzip",
  "grid": { "origin": [-180, -90], "dlon": 0.05, "dlat": 0.025, "chunk": 4,
            "row0": 6124, "col0": 3748, "rows": 44, "cols": 52 },
  "times": [ … ],                 // union of all variables' valid times, sorted
  "variables": [ {name, unit, scale, offset, nodata, min, max, wrap?, product,
                  segments: [{source, run_id, start, end, step_hours}]}, … ],
  "availability": {x0: cx0, y0: cy0, width, height, count, bits},
  "ocean_only": false             // true: chunks without ocean data were not written
}
```

- Lattice cell `(r, c)`: `r = floor((lat + 90) / dlat)`, `c = floor((lon + 180) / dlon)`; chunk
  `cy = floor(r / chunk)`, `cx = floor(c / chunk)`; inside the chunk `row = r − cy·chunk`
  (south → north), `col = c − cx·chunk` (west → east).
- File: gzip of `b"WLS1"` + uint16 LE `rows, cols, nvars, ntimes` + uint8 codes
  `[var][row][col][time]`. Code 255 = no data (e.g. a variable outside its segments' times).
  If a proxy already removed the gzip layer, the bytes start with `WLS1` directly.
- Values: same encodings as the tile channels. Cell values are bilinear at the cell centre; for
  ocean variables the coastline rule is relaxed (any of the 2×2 surrounding native cells with data
  counts), so a coastal cell borrows the adjacent sea value up to about one native cell inland.

## Versioning rules

- **Patch** (1.0.x): documentation or value-range clarifications, no structural change.
- **Minor** (1.x.0): new optional fields, new layers/products/sources, new zoom levels. Clients
  must ignore unknown fields and unknown layer ids.
- **Major** (2.0.0): anything that changes meaning (encoding, paths, conventions) or removes
  fields. Clients check the major version (`SUPPORTED_MAJOR` in `web/layer/src/core/manifest.ts`)
  and refuse an unknown major with a clear error.
- The tile encoding is described per channel in the manifest; clients must read `scale`,
  `offset` and `nodata` from there rather than hard-coding them.

## Attribution (required wording)

- MET Norway (NLOD 2.0 / CC BY 4.0): "Based on data from MET Norway".
- ECMWF (CC BY 4.0): "This service is based on data and products of the European Centre for
  Medium-Range Weather Forecasts (ECMWF)", with a link to www.ecmwf.int, the CC BY 4.0 licence,
  the note that the data was modified (regridded and tiled) and ECMWF's disclaimer: "ECMWF does
  not accept any liability whatsoever for any error or omission in the data, their availability,
  or for any loss or damage arising from their use."
- Both strings are in `manifest.attribution[]`; the React `Attribution` component renders them.
