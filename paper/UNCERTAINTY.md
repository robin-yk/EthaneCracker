# TEA parameter calibration and uncertainty

Compression duty is calibrated to Chen (2024), and effective fired efficiency to Shin (2025). The calculation uses uniform parameter ranges and three assumed model–literature discrepancy scales. Each heating-route pair shares its process-parameter draw. Equations, ranges and sources are recorded in [the method](../uncertainty/README.md).

## Parameter estimates

| Assumed discrepancy σ | Fired efficiency (%) | Compression multiplier |
|---|---:|---:|
| 5% | 56.75 / 62.75 / 70.25 | 1.100 / 1.231 / 1.353 |
| 10% | 52.75 / 63.75 / 79.00 | 0.988 / 1.231 / 1.475 |
| 20% | 48.00 / 65.00 / 83.50 | 0.753 / 1.231 / 1.709 |

Values show the 2.5th percentile, median, and 97.5th percentile.

## Paired economics

Reference: 850 °C, 0.35 s, 610 kt/y; natural gas $4/GJ. Joule efficiency is 95%, with equal furnace capital factors. Each scenario uses 512 shared-parameter draws.

| Assumed discrepancy σ | Break-even electricity (cents/kWh) | Joule − fired at $0.07/kWh ($/t) |
|---|---:|---:|
| 5% | 1.93 / 2.19 / 2.41 | 187.2 / 196.3 / 206.7 |
| 10% | 1.72 / 2.16 / 2.57 | 180.8 / 197.0 / 215.6 |
| 20% | 1.63 / 2.14 / 2.82 | 170.5 / 198.4 / 219.0 |

For equal reactor conditions and furnace factors, the model gives `p_e* = 0.0036 × p_g × η_J / η_F`. Common process costs cancel in the difference. The dashboard also reports furnace capital factors of 0.7 and 1.3 and Joule efficiencies of 90% and 98%.

Numerical results and source hashes: [results.json](../uncertainty/results.json).
