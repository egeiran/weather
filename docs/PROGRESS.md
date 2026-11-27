# Progress

| # | Milestone | Status |
|---|-----------|--------|
| 0 | Bootstrap (layout, tooling, CLAUDE.md, README) | done |
| 1 | Data spike, data-sources.md, packaging decisions | done |
| 2 | Pipeline core: MEPS wind + gusts | done |
| 3 | Layer core + demo + Playwright | done |
| 4 | Waves + currents | done (WW3 4 km, NorKyst v3) |
| 5 | ECMWF days 3–10, stitching | done |
| 6 | Particles | done |
| 7 | Click for values + thresholds | done |
| 8 | Hardening, cross-check, full-coast run | pending |
| 9 | Docs + independent review | pending |

## Next

- M8: MET cross-check report, performance budget measurement, full-coast run, error states.
- M9: architecture/contract/host-integration/deployment docs, independent review.
- Waiting for the owner's pick of look options (artifact "Værlagets utseende"); defaults: calm ramp, hatching, arrows + particles 'auto'.

## Open issues

- MyWaveWAM 4 km is gone → WW3 4 km (decision 0004). NorKyst800 v2 is gone → NorKyst v3.
- Coast data volume: balanced defaults (decision 0007); banded fetch not yet implemented.
- Headless screenshots use SwiftShader (software WebGL): particle trails look shorter than on real GPUs.
