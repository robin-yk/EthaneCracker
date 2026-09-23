# Literature benchmark protocol

The benchmark page evaluates Chen (2024), Shin (2025), and Wang (2026) using the same engine as the simulator. Current numerical results are in [results.json](results.json) and the [benchmark page](index.html).

| Case | Input reconstruction | Compared outputs |
|---|---|---|
| Chen 2024 | Infer residence time from residual ethane; evaluate the two reported pressure alternatives | Product composition, fresh feed, reactor heat, compressor electricity |
| Shin 2025 | Infer residence time from fresh-feed demand across 800–900 °C and 1–5 bar | C3+ production, total combustion energy, on-site emissions |
| Wang 2026 | Derive residence time from geometry; search the declared heating-ramp range | Conversion, recycle, product composition |

Residence-time searches use the loaded GP domain. `fit` labels quantities used to reconstruct inputs; `test` labels other compared outputs. `context` keeps economic values with different financial or equipment boundaries alongside the model calculation.

The uncertainty analysis uses Chen compression electricity and Shin combustion energy to estimate effective process coefficients. Those two values are calibration inputs in that analysis. See [the calculation method](../uncertainty/README.md).

The Literature benchmark replay workflow regenerates the numerical results. The main workspace reads its comparison cards from the same result file.

Sources and operating assumptions are recorded in [literature.json](literature.json).
