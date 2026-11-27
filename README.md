# weather-layers

Windy-style weather surfaces (wind, gusts, waves, swell, currents) for a MapLibre vessel map,
built from open MET Norway and ECMWF forecasts. No server, no keys, no Docker: a Python job writes
static files, a TypeScript module draws them.

> Work in progress — see [docs/PROGRESS.md](docs/PROGRESS.md).

## Quick start

```sh
make setup      # uv sync + npm install + Playwright browser
make pipeline   # fetch + build the development area (Frøya/Hitra) into data/out
make dev        # demo on http://localhost:5173
```

## Docs

- [Architecture](docs/architecture.md) · [Data sources](docs/data-sources.md) · [Contract](docs/contract.md)
- [Host integration](docs/host-integration.md) · [Deployment](docs/deployment.md) · [Decisions](docs/decisions/)

Data: MET Norway (CC BY 4.0 / NLOD), ECMWF (CC BY 4.0). Basemap: OpenFreeMap © OpenMapTiles © OpenStreetMap contributors.
