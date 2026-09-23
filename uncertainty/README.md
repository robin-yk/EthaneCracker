# Literature calibration and paired TEA uncertainty

Open `uncertainty/index.html` through a local HTTP server, or follow **Model → Literature calibration & uncertainty** in the simulator. The saved result can be inspected immediately; Recalculate runs the same engine and exports JSON.

This is a conditional calibration of a screening process model against published process-simulation outputs. It does not identify physical equipment efficiencies uniquely, establish experimental accuracy, or validate the financial boundaries of the compared papers. The default simulator remains unchanged unless research parameters are explicitly passed to the API.

## Evidence and boundary audit

| Evidence | Use | Boundary and source |
|---|---|---|
| Chen 2024, residual ethane 15.1 mol% | Reconstruct residence time | Two discrete pressure alternatives, 1 and 4.5 bar, reflect inconsistent source descriptions. Both receive equal prior weight. |
| Chen, C101 power 29.4 MW / ethylene 79.4 t/h | Fit an effective compression multiplier | Table 2 identifies electricity to C101. Source compressor discharge is approximately 30 bar; this engine uses 32 bar and a fixed 1.5 bar suction. The multiplier absorbs flow, equipment and boundary differences; it is not an inferred isentropic efficiency. |
| Shin 2025, fresh ethane / ethylene inventory | Reconstruct missing operating states | Scan 800–900 °C in 5 °C steps and 1–5 bar in 0.5 bar steps. Infer residence time on 0.02–1.5 s and retain states within 0.5% of reported fresh-feed demand. Equal prior weight on retained discrete states is an assumption. |
| Shin, total combustion energy 17.2 GJ/t | Fit effective fired efficiency | Includes imported natural gas and purge fuel. Compare to engine total heater input, not purchased natural gas alone. |
| Other species, feed and emissions outputs | Held-out output checks | Excluded from utility calibration. They are outputs of the same studies and can share modeling assumptions. |
| Chen reactor duty | Boundary-difference diagnostic | The source reports high-temperature fuel-gas duty; the engine comparator is the Cantera enthalpy rise from 650 °C. Do not fit this difference by changing heat recovery. |
| Reported MSP, manufacturing cost and CAPEX | Excluded from likelihood | Discounted MSP versus screening cost, purchased versus installed equipment, and overhead definitions have not been reconciled. No capital posterior is claimed. |
| Wang 2026 | Excluded | The benchmark records incompatible reactor inlet temperature, inlet composition and kinetic history. |

Sources: [Chen et al., DOI 10.1039/D3GC03858K](https://doi.org/10.1039/D3GC03858K), [author institution copy](https://udspace.udel.edu/server/api/core/bitstreams/918f00c2-5f7d-40b8-9a1b-939585b06019/content); [Shin et al., DOI 10.1039/D4GC04538F](https://doi.org/10.1039/D4GC04538F). The existing machine-readable transcription is `benchmarks/literature.json`. Chen's power and heat-duty definitions were checked in Tables 1–2 and section 3.3. Shin's combustion-energy value is confirmed in indexed publisher text; the other inventory entries are inherited from the repository transcription. They have not all been independently re-extracted in this change.

## Inverse calculation

For each reconstructed state z and calibration parameter θ, use

`weight(θ,z) ∝ prior(θ) prior(z) exp[-0.5 ((model(θ,z) − observation)/σ)^2]`.

Each one-dimensional parameter integral uses 161 evenly spaced nodes and trapezoidal endpoint weights. Discrete nuisance-state weights are normalized jointly with parameter weights. The two studies are treated as conditionally independent. Reactor-state reconstruction is conditioned on point estimates; its source measurement uncertainty is not inferred.

| Parameter | Prior / scenario | Data update |
|---|---|---|
| Effective fired efficiency | Uniform 45–85% | Shin combustion energy |
| Effective compression multiplier | Uniform 0.5–2.0 | Chen C101 electricity |
| Heat-recovery fraction | Uniform 0.5–0.9 | None; scenario assumption |
| Shared capital multiplier | Uniform 0.7–1.5 | None; scenario assumption |
| Joule efficiency | Separate 90%, 95%, 98% cases | None |
| Joule furnace capital multiplier | Separate 0.7, 1.0, 1.3 cases | None; scales furnace contribution only |

**All bounds and distribution shapes above are analyst assumptions.** They are not reported confidence intervals or universal engineering bounds. Gaussian σ is tested at 5%, 10% and 20% of each reported utility value. It represents an assumed aggregate mismatch, including model and boundary differences. It is not an estimated measurement standard deviation. Explicit GP posterior uncertainty, correlated study errors, price uncertainty, structural model averaging and operating-condition optimization are outside this calculation.

The compression multiplier preserves the existing compressor physics and scales its duty. Fired efficiency scales total heater demand through `Qin = Quseful/(eff/100)`. No non-identifiable heat-recovery or capital parameter is squeezed into a narrow posterior using the same two observations. Boundary mass is recorded to help detect truncation by prior limits.

## Paired propagation

Draw the calibrated parameters and shared heat recovery/capital parameters with a fixed random seed (20260923), 512 draws per scenario. Use each draw for both heating routes at the same 850 °C, 0.35 s, dilution 0.35, 1.5 bar, ramp exponent 1, and 610 kt/y capacity. Gas costs $4/GJ; the reference electricity price is $0.07/kWh. These are explicit reference assumptions rather than current market prices.

For each pair, report absolute cost distributions and `ΔC = C_Joule − C_fired`. Under this engine, cost is affine in electricity price. Two API endpoint evaluations per route determine the exact crossing; direct evaluations at that crossing are regression-tested. Negative crossings are retained. Empirical cheaper-draw fractions describe this conditional distribution. Monte Carlo Wilson intervals are recorded so a zero count does not imply a mathematically zero probability.

Shared compression, separation, heat-recovery credit and capital cancel in the difference when chemistry and furnace factors are identical. They still change absolute costs. This cancellation is a structural assumption of this comparison. A Joule-specific furnace multiplier tests one source of differential capital cost. Power electronics, electrode replacement, route-specific labor, changed operating conditions and different steam-export requirements have not been separately designed or calibrated.

For equal furnace factors the current engine also values sold tail gas at the purchased-gas price. Its paired crossing reduces exactly to `electricity_price* = 0.0036 × gas_price × Joule_efficiency / fired_efficiency`. Chemistry and common process costs cancel from this expression. A regression checks the numerical API crossing against this identity. The result quantifies uncertainty in the assumed energy substitution, rather than demonstrating a kinetic advantage of Joule heating. Distinct operating histories would require a separate comparison.

Held-out intervals include parameter variation only. They are not posterior predictive intervals with added observation/model-discrepancy noise. The dashboard displays failures as well as agreements. A successful software test never converts a failed literature comparison into a validation success.

## Reproduce

```sh
npm install --no-save playwright
npx playwright install chromium
node --test uncertainty/test-analysis.mjs
node uncertainty/run.mjs
node uncertainty/check-results.mjs
```

Python is used only to serve the repository. `CHROMIUM_EXECUTABLE_PATH` optionally selects an installed Chromium. The runner executes live-engine regressions and records SHA256 hashes of the engine, source data, GP artifact and analysis code in `results.json`. `node uncertainty/run.mjs --check-only` runs just the live-engine checks. The existing browser fuzz suite continues to cover heating-efficiency rejection and GP-domain boundaries.

The approach is related to computer-model calibration: [Kennedy & O'Hagan (2001), DOI 10.1111/1467-9868.00294](https://doi.org/10.1111/1467-9868.00294). This implementation uses explicit discrete quadrature and assumed scalar discrepancy scales; it does not implement the full Kennedy–O'Hagan discrepancy GP.
