# TEA parameter calibration and uncertainty

Compression duty is calibrated to Chen (2024), and effective fired efficiency to Shin (2025). The calculation uses uniform parameter ranges and three assumed model–literature discrepancy scales. Each heating-route pair shares its process-parameter draw. Equations, ranges and sources are recorded in [the method](../uncertainty/README.md).

## Parameter estimates

| Assumed discrepancy σ | Fired efficiency (%) | Compression multiplier |
|---|---:|---:|
| 5% | 56.75 / 63.00 / 70.50 | 1.100 / 1.222 / 1.344 |
| 10% | 53.00 / 63.75 / 79.00 | 0.978 / 1.222 / 1.466 |
| 20% | 48.00 / 65.00 / 83.50 | 0.744 / 1.222 / 1.700 |

Values show the 2.5th percentile, median, and 97.5th percentile.

## Paired economics

Reference: 850 °C, 0.35 s, 610 kt/y; natural gas $4/GJ. Surplus tail gas is burned without sales revenue. Joule efficiency is 95%, with equal furnace capital factors. Each scenario uses 512 shared-parameter draws.

| Assumed discrepancy σ | Break-even electricity (cents/kWh) | Joule − fired at $0.07/kWh ($/t) |
|---|---:|---:|
| 5% | 0.91 / 1.15 / 1.37 | 230.7 / 239.7 / 249.8 |
| 10% | 0.68 / 1.14 / 1.54 | 223.7 / 240.4 / 259.0 |
| 20% | 0.61 / 1.11 / 1.79 | 213.4 / 241.4 / 262.1 |

For equal reactor conditions and furnace factors, with surplus tail gas burned, the model gives `p_e* = 0.0036 × p_g × purchased_fired_gas / Joule_heater_input` (both energy quantities in GJ/t). Common process costs cancel in the difference. The dashboard also reports furnace capital factors of 0.7 and 1.3 and Joule efficiencies of 90% and 98%.

Numerical results and source hashes: [results.json](../uncertainty/results.json).
