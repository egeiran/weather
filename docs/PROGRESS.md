# Progress

| # | Milestone | Status |
|---|-----------|--------|
| 0 | Bootstrap (layout, tooling, CLAUDE.md, README) | done |
| 1 | Data spike, data-sources.md, packaging decisions | done |
| 2 | Pipeline core: MEPS wind + gusts | in progress (generic modules + tests exist) |
| 3 | Layer core + demo + Playwright | pending |
| 4 | Waves + currents | pending |
| 5 | ECMWF days 3–10, stitching | pending |
| 6 | Particles | pending |
| 7 | Click for values + thresholds | pending |
| 8 | Hardening, cross-check, full-coast run | pending |
| 9 | Docs + independent review | pending |

## Next

- M2: manifest JSON Schema, tests for series/stitching/retention/atomic publish.
- M3: layer core + demo.

## Open issues

- MyWaveWAM 4 km is gone → WW3 4 km (decision 0004). NorKyst800 v2 is gone → NorKyst v3.
- Coast data volume: balanced defaults (decision 0007); banded fetch not yet implemented.
