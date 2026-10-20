# Cold box: physics reference and validation

The engine solves the cold box itself (`coldBox()` in `engine.html`): a Peng–Robinson flash at 30 bar sets the cold end that leaves 0.5 % of the ethylene in the tail gas, and an enthalpy balance over the cooling curve gives the refrigeration duty at the −40 °C, −100 °C and cold-end levels. This folder holds the independent Python calculation the engine is checked against, and the refrigeration-cycle calculation that supplies the cascade coefficients of performance.

## Assumptions in the engine

| Assumption | Value | Source |
|---|---|---|
| Cold-box pressure | 30 bar | compressor discharge 32 bar less drying and chilling-train drop |
| Ethylene recovery, one equilibrium stage | 99.5 % | design specification; a chilling train with a demethanizer reaches it with a warmer overhead, so the single stage is the hydrogen-removal bound |
| Approach temperature in the feed exchangers | 5 K | plate-fin practice |
| Return temperatures | tail gas 25 °C, condensate −30 °C | condensate cold is used down to the C2-splitter condenser level |
| Equation of state | Peng–Robinson, ChemSep kij | `thermo` library (Bell and co-workers) interaction-parameter table |
| Ideal-gas enthalpy | NASA polynomials | McBride, Gordon and Reno; Cantera `nasa_gas.yaml`, 200–1000 K fits used down to the cold end |
| Refrigeration cascade | propylene / ethylene / methane, two-stage economized, COP 1.69 / 1.45 / 2.88; C2-splitter condenser on propylene, COP 2.07 | `refrigeration_cycles.py` (CoolProp; 5 K approach, 30 °C cooling water, isentropic efficiency 0.75, no motor losses) |

## Files

| File | What it is |
|---|---|
| `coldbox_vle.py`, `coldbox_duty.py`, `coldbox_point.py` | The same physics with the `thermo` library: flash to the recovery, 1 K cooling curve with tail-gas and condensate recuperation, duty by level. Results for the reference and Wang (2026) cases: `coldbox-vle-results.json`, `coldbox-duty-results.json`. |
| `refrigeration_cycles.py`, `refrigeration-cycles-results.json` | Cascade cycles from CoolProp, single-stage and two-stage. |
| `coldbox-feeds.json`, `wang-gp-inventory.json` | Cold-box feed inventories the engine (commit `fbb03d8`) computes over COT 760–900 °C × τ 0.2–1.5 s × n {0.5, 1, 4} × steam/ethane {0.2, 0.35, 0.5} × P {1.5, 3} bar, and the Wang GP case. |
| `coldbox-reference.csv` | The Python physics at 1,234 compositions: the engine grid, 240 compositions with methane, C3+ and hydrogen scaled at random (0.5–3, 0.5–3, 0.7–1.4), and the named cases. |
| `check_engine.cjs` | Runs the engine's `coldBox()` on every reference composition and reports the cold-end and refrigeration-work deviations, then prints the reference fired case. |

Validation (2026-10-14): 1,232 compositions, cold end rmse 0.004 K (max 0.04 K), refrigeration work rmse 0.12 % (max 1.3 %, hydrogen-rich feeds where the Cp data differ). The remaining difference comes from the ideal-gas heat capacities (NASA polynomials against the thermo correlations) and the 10 K step of the enthalpy balance against 1 K.

Python environment: `~/.venvs/ethane-coldbox` (numpy, scipy, thermo 0.6.1, CoolProp 8.0).

## Limits

Single-stage flash for hydrogen removal and no demethanizer column; no cold-box pressure drop; no refrigerant-compressor motor losses; constant methane-cycle COP; tail-gas expansion not evaluated.
