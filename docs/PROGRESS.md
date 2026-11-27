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
| 8 | Hardening, cross-check, full-coast run | done |
| 9 | Docs + independent review | pending |

## Results so far

- Cross-check (docs/crosscheck.md): tiles at MET's grid point agree within wind 0.05 m/s / 0.9°,
  current 0.05 kn / 2.9°, sea temperature 0.04 °C; waves 0.14 m / 10° (WW3 vs MET's WAM 800 m).
- Performance (docs/performance.md): first view ≤ 398 KB, step change ≤ 177 KB, click = 1 request,
  60 fps with particles.
- Full coast: 4 min 42 s, 1.87 GB downloaded, 268 MB public / 371 MB state, 17,631 files; no-op 4.3 s.

## Next

- M9: independent cold review by a subagent, fix findings, final report.
- Owner's pick of look options (artifact "Værlagets utseende") — defaults: calm, hatching, arrows + particles 'auto'.

## Open issues

- Row-band fetching for rotated grids (WW3, NorKyst) not implemented (≈ −⅓ download).
- Swell has no data after +66 h (ECMWF open data has no partitions); currents end at +120 h.
- Headless screenshots use SwiftShader (software WebGL): particle trails look shorter than on real GPUs.
- Globe projection not supported by the custom layer (mercator only).
