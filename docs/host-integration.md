# Host integration (Fleet Tracker)

The integration has three parts: the host **serves the files** (with its own auth), the host
frontend **mounts the layer** (with an authenticated fetch) and **drives time**. Nothing in the
browser talks to MET Norway or ECMWF.

## 1. Serving the files behind the host's authentication

Plain static files, no Range requests needed (XYZ tiles, see decision 0001). Requirements:

- `GET <prefix>/manifest.json` → `Cache-Control: no-cache` (or `max-age=60`).
- `GET <prefix>/runs/**` and `<prefix>/series/**` → `Cache-Control: private, max-age=31536000, immutable`
  (paths contain the run id and never change; `private` because they sit behind auth).
- Content types: `.json` → `application/json`, `.png` → `image/png`, `.bin` → `application/octet-stream`.
  Do **not** add `Content-Encoding: gzip` to `.bin` files (they are already gzip inside); if a proxy
  compresses or decompresses them anyway, the client copes (it checks the magic bytes).
- 404 for missing files is fine (the client avoids them via the manifest's availability bitsets).
- Reject path traversal; only serve `manifest.json`, `runs/`, `series/`.

Example: a Next.js 16 route handler that serves the pipeline's output directory to signed-in
users (adapt `requireUser` and `WEATHER_DATA_DIR` to the host):

```ts
// app/api/weather/[...path]/route.ts
import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { Readable } from 'node:stream';

const ROOT = resolve(process.env.WEATHER_DATA_DIR ?? '/var/lib/weather-layers/out');
const TYPES: Record<string, string> = { json: 'application/json', png: 'image/png', bin: 'application/octet-stream' };

export async function GET(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  await requireUser(req); // host's own auth; throw/return 401 when not signed in
  const rel = (await params).path.join('/');
  if (!/^(manifest\.json|(runs|series)\/[\w./-]+)$/.test(rel) || rel.includes('..')) {
    return new Response('bad path', { status: 400 });
  }
  const file = resolve(ROOT, rel);
  if (!file.startsWith(ROOT + sep)) return new Response('bad path', { status: 400 });
  const info = await stat(file).catch(() => null);
  if (!info?.isFile()) return new Response(null, { status: 404 });
  const ext = rel.split('.').pop()!;
  return new Response(Readable.toWeb(createReadStream(file)) as ReadableStream, {
    headers: {
      'Content-Type': TYPES[ext] ?? 'application/octet-stream',
      'Content-Length': String(info.size),
      'Cache-Control':
        rel === 'manifest.json' ? 'no-cache' : 'private, max-age=31536000, immutable',
    },
  });
}
```

With blob storage instead of a local directory, the handler streams the object with the same
headers (or redirects to a short-lived signed URL — then the injected fetch must follow redirects,
which `fetch` does by default). The demo's Vite middleware (`web/demo/vite.config.ts`) is a
working reference that also enforces a bearer token.

## 2. Mounting the layer in the host frontend

The module is TypeScript source with two entry points: `weather-layers` (framework-agnostic
core) and `weather-layers/react` (adapter + UI). Peer dependencies: `maplibre-gl` ^6.8, and for the
adapter `react` ^19 and `react-map-gl` ^8.1.

Install (monorepo workspace or copied package) and let Next.js transpile it:

```js
// next.config.js
export default { transpilePackages: ['weather-layers'] };
```

Inside the host's `react-map-gl/maplibre` `<Map>` (client component):

```tsx
'use client';
import 'weather-layers/styles.css';
import { DEFAULT_THRESHOLDS, type LayerId, type WeatherState } from 'weather-layers';
import { WeatherI18nProvider, WeatherOverlay, Legend, StatusBar, PointPanel, Attribution } from 'weather-layers/react';

// The host injects its own authenticated fetch; every data request goes through it.
const authFetch = (url: string, init?: RequestInit) =>
  fetch(url, { ...init, credentials: 'include', headers: { ...init?.headers, Authorization: `Bearer ${getToken()}` } });

export function WeatherOverlayForFleet({ time, layer, visible }: { time: Date; layer: LayerId; visible: boolean }) {
  const [state, setState] = useState<WeatherState | null>(null);
  return (
    <WeatherI18nProvider locale="nb">
      <WeatherOverlay
        baseUrl="/api/weather/"
        fetch={authFetch}
        layer={layer}
        time={time}                 // the host timeline drives this
        visible={visible}           // toggled like any other overlay
        particles="auto"            // off with prefers-reduced-motion / slow connection
        thresholds={DEFAULT_THRESHOLDS}
        theme={isDarkBasemap ? 'dark' : 'light'}
        onState={setState}          // status, range, loading, errors
      />
      <div className="wl-root" data-theme={isDarkBasemap ? 'dark' : 'light'}>
        <Legend state={state} />
        <StatusBar state={state} />
        <Attribution state={state} />
      </div>
    </WeatherI18nProvider>
  );
}
```

- **Ready-made UI** (`weather-layers/react`): `LayerRail`, `Legend`, `SettingsMenu` (gear popover,
  takes extra sections as children), `TimeSlider` (shows model/run/valid time), `StatusBar` (only
  warnings), `PointPin` (draggable react-map-gl Marker with the active value) and `PointPanel`.
  Theme with `<div className="wl-root" data-theme="dark">`. Hosts may use their own UI instead.
- **Coastline:** a thin coastline is drawn above the weather field from the basemap's vector
  `water` layer (OpenMapTiles schema). Pass `coastline={{ source, sourceLayer }}` for another
  basemap or `coastline={false}` to turn it off.
- **Layer order:** the weather layer is inserted below the first symbol layer of the basemap
  (labels stay on top). Add the host's vessel/site layers after it, or pass `beforeId`.
- **Style switches:** the layer re-attaches itself on `style.load` (light/dark basemap swaps).
- **Without React:** `new WeatherLayers({ baseUrl, fetch: authFetch }).addTo(map)` and call the
  setters; subscribe with `controller.on('change', state => …)`.

## 3. Driving time from the host timeline

- `state.range` (or `controller.getTimeRange()`) is the union range of all layers; clamp the
  host timeline's start to "now" and its end to `range.end` (~10 days).
- Pass any `Date` to `time` / `setTime()`. The module snaps to the nearest valid step of the
  active layer within half a step; outside a layer's data it draws nothing and reports
  `status: 'no-data'` with the layer's range (the `StatusBar` shows a message).
- `state.resolved` tells which model and run is shown (`segment.label`, e.g. "MEPS 06Z"), the valid
  time and the step length; `manifest.layers[id].segments` give the model/step bands for the
  host's own timeline (see `TimeSlider` for a reference rendering).
- `controller.stepTime(+1 | -1)` returns the next/previous valid time of the active layer.

## 4. Click for values

`await controller.queryPoint({ lng, lat })` → values of all variables for the whole timeline,
the nearest-step values, and first threshold exceedance per threshold. It costs one request
(the series chunk, ~7–10 KB gzip) and is cached per manifest. `PointPanel` renders it.

## 5. If this repo moves into the monorepo

Copy, keeping paths relative to each other:

| from | to (suggestion) | notes |
|---|---|---|
| `pipeline/` | `apps/weather-pipeline/` | its own uv project; scheduled job (docs/deployment.md) |
| `web/layer/` | `packages/weather-layers/` | npm workspace package `weather-layers`; add to `transpilePackages` |
| `schema/` | `packages/weather-layers/schema/` or shared `schema/` | update `SCHEMA_PATH` in `pipeline/src/weather_layers/schema.py` |
| `docs/` | `apps/weather-pipeline/docs/` | keep decisions with the code |
| `web/demo/` | optional (`apps/weather-demo/`) | handy for visual checks and Playwright |

Keep the contract: the pipeline writes the output directory, the host serves it, the module
reads it. Version both sides together when `schema_version` changes major.
