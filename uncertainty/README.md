# TEA calibration and uncertainty

Open `uncertainty/index.html` through a local HTTP server, or follow **Model → Literature calibration & uncertainty** in the simulator. The saved result can be inspected immediately; Recalculate runs the same engine and exports JSON.

Published utility values are used to estimate effective fired efficiency and a compression-duty multiplier. Heat recovery and capital vary over specified ranges. Results are conditional on the process equations, parameter ranges and discrepancy scales below.

## Literature inputs

| Evidence | Use | Boundary and source |
|---|---|---|
| Chen 2024, residual ethane 15.1 mol% | Reconstruct residence time | Two discrete pressure alternatives, 1 and 4.5 bar, reflect inconsistent source descriptions. Both receive equal prior weight. |
| Chen, C101 power 29.4 MW / ethylene 79.4 t/h | Fit an effective compression multiplier | Table 2 identifies electricity to C101. Source compressor discharge is approximately 30 bar; this engine uses 32 bar and a fixed 1.5 bar suction. The fitted multiplier scales compressor duty and includes differences in flow and equipment assumptions. |
| Shin 2025, fresh ethane / ethylene inventory | Reconstruct missing operating states | Scan 800–900 °C in 5 °C steps and 1–5 bar in 0.5 bar steps. Infer residence time on 0.02–1.5 s and retain states within 0.5% of reported fresh-feed demand. Equal prior weight on retained discrete states is an assumption. |
| Shin, total combustion energy 17.2 GJ/t | Fit effective fired efficiency | Includes imported natural gas and purge fuel. The corresponding model quantity is total heater input. |
| Other species, feed and emissions outputs | Held-out output checks | Excluded from utility calibration. They are outputs of the same studies and can share modeling assumptions. |
| Chen reactor duty | Boundary-difference diagnostic | The source reports high-temperature fuel-gas duty; the engine comparator is the Cantera enthalpy rise from 650 °C. Retained as a comparison quantity. |
| Reported MSP, manufacturing cost and CAPEX | Excluded from likelihood | The studies use different financial periods, equipment-cost definitions and overheads. Capital retains its specified distribution. |
| Wang 2026 | Excluded | The benchmark records incompatible reactor inlet temperature, inlet composition and kinetic history. |

Sources: [Chen et al., DOI 10.1039/D3GC03858K](https://doi.org/10.1039/D3GC03858K), [author institution copy](https://udspace.udel.edu/server/api/core/bitstreams/918f00c2-5f7d-40b8-9a1b-939585b06019/content); [Shin et al., DOI 10.1039/D4GC04538F](https://doi.org/10.1039/D4GC04538F). Values and source notes are stored in `benchmarks/literature.json`. Chen utility definitions were checked against Tables 1–2 and section 3.3; Shin combustion energy was checked against publisher text. Other inventory values use the repository transcription.

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

The ranges and distributions are specified for this analysis. Gaussian σ is set to 5%, 10% or 20% of each reported utility value to represent model–literature discrepancy. GP posterior error, correlations between studies, prices and operating conditions are held fixed in this propagation.

The compression multiplier preserves the existing compressor physics and scales its duty. Fired efficiency scales total heater demand through `Qin = Quseful/(eff/100)`. Heat recovery and capital retain their input distributions. Probability mass near each parameter bound is recorded.

## Paired propagation

Draw the calibrated parameters and shared heat recovery/capital parameters with a fixed random seed (20260923), 512 draws per scenario. Use each draw for both heating routes at the same 850 °C, 0.35 s, dilution 0.35, 1.5 bar, ramp exponent 1, and 610 kt/y capacity. Gas costs $4/GJ; the reference electricity price is $0.07/kWh. These prices are fixed calculation inputs.

For each pair, report absolute cost distributions and `ΔC = C_Joule − C_fired`. Under this engine, cost is affine in electricity price. Two API endpoint evaluations per route determine the exact crossing; direct evaluations at that crossing are regression-tested. Negative crossings are retained. Empirical cheaper-draw fractions describe this conditional distribution. Wilson intervals quantify sampling uncertainty in the cheaper-draw fraction.

Shared compression, separation, heat-recovery credit and capital cancel in the difference when chemistry and furnace factors are identical. They still change absolute costs. The Joule furnace multiplier varies furnace capital. Power electronics, electrode replacement and route-specific labor have no separate cost terms; operating conditions and steam-export assumptions are shared.

The reference case burns surplus tail gas without a sale credit. At equal furnace factors its crossing is `electricity_price* = 0.0036 × gas_price × purchased_fired_gas / Joule_heater_input`, with both energy quantities in GJ/t. For the sell-surplus option at the purchased-gas price, this reduces to `0.0036 × gas_price × Joule_efficiency / fired_efficiency`. Regression tests check both identities against direct API evaluations.

Comparison intervals contain propagated parameter variation. Observation noise and discrepancy noise are excluded from those intervals. Each table reports whether the published value falls within the calculated range.

## Reproduce

```sh
npm install --no-save playwright
npx playwright install chromium
node --test uncertainty/test-analysis.mjs
node uncertainty/run.mjs
node uncertainty/check-results.mjs
```

Python is used only to serve the repository. `CHROMIUM_EXECUTABLE_PATH` optionally selects an installed Chromium. The runner executes live-engine regressions and records SHA256 hashes of the engine, source data, GP artifact and analysis code in `results.json`. `node uncertainty/run.mjs --check-only` runs just the live-engine checks. The existing browser fuzz suite continues to cover heating-efficiency rejection and GP-domain boundaries.

The approach is related to computer-model calibration: [Kennedy & O'Hagan (2001), DOI 10.1111/1467-9868.00294](https://doi.org/10.1111/1467-9868.00294). This implementation uses discrete quadrature and specified scalar discrepancy scales.
