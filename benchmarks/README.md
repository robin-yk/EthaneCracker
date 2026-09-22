# Literature benchmark protocol

The benchmark page replays published ethane-cracker cases through the same `model()` and `lca()` functions used by the root web app. The process replay includes AC-201 selective acetylene hydrogenation before cryogenic separation and the C2 splitter.

Each case separates **fit**, **test**, and **context** quantities.

- **fit**: one published quantity determines one unreported reactor coordinate.
- **test**: the quantity stays outside the fit and tests the resulting calculation.
- **context**: the paper and web model use different TEA/LCA boundaries, so both values are retained without treating their difference as a model error.

## Chen et al., Green Chemistry 2024

DOI: 10.1039/D3GC03858K

Published reactor information includes 950 °C, an ethane:steam volume ratio of 3:1, and outlet dry-gas fractions of 37.7% C2H4, 40.7% H2, 3.3% CH4, and 15.1% C2H6. The process description states ambient reactor pressure; Table 1 reports 4.5 bar. The benchmark evaluates both pressures.

Residence time is determined from the 15.1 mol% residual ethane:

- inferred residence time: **0.106–0.143 s**
- C2H4: published **0.377**, model **0.371–0.384 mol/mol**
- H2: published **0.407**, model **0.396–0.412 mol/mol**
- CH4: published **0.033**, model **0.035–0.060 mol/mol**
- fresh ethane: published **1.108**, model **1.248–1.272 kg/kg ethylene**
- high-temperature reactor heat: published **5.25**, model **7.79–7.83 GJ/t**
- compressor work: published **370**, model **299–309 kWh/t**

The major reactor species distribution transfers well after one residence-time constraint. Fresh-feed selectivity and thermal duty remain higher than the published Aspen case.

## Shin et al., Green Chemistry 2025

DOI: 10.1039/D4GC04538F

The main article reports a steam/ethane ratio of 0.33, fresh ethane of 151,182 kg/h, ethylene of 114,335 kg/h, C3+ of 15,738 kg/h, combustion heat of 17.2 GJ/t ethylene, on-site GHG of 442 kgCO2e/t before allocation, LCOE of $746/t, and WTG GHG of 869 kgCO2e/t. One reactor temperature/residence-time/pressure triplet is absent from the main article.

For each point on an 800–900 °C and 1–5 bar grid, residence time is determined from fresh ethane demand. Seventeen states satisfy the 0.5% feed criterion.

Independent outputs across those states:

- C3+: published **0.1376**, model **0.1145–0.1303 kg/kg**
- combustion heat: published **17.2**, model **17.50–18.43 GJ/t**
- on-site GHG: published **442**, model **442–507 kgCO2e/t**

The published combustion-energy and on-site GHG values fall close to or inside the model envelope while C3+ production is 5–17% lower.

## Wang et al., Frontiers in Energy Research 2026

DOI: 10.3389/fenrg.2026.1726062

The conventional ethane-cracker case reports 840 °C, 3.2 bar, 245 tubes with 10.5 m length and 0.085 m diameter, 194.28 t/h reactor feed, 45 t/h steam, and detailed inlet/outlet compositions.

Published geometry gives:

- total reactor volume: **14.60 m3**
- residence time at mean T/P: **0.291 s**
- inlet/outlet-state residence bracket: **0.243–0.360 s**

The published outlet composition gives a single-pass ethane conversion of **0.685**. The Aramco GP reaches **0.390** at the fastest allowed heating history, (n=0.45).

Additional comparisons at the Aramco domain edge:

- fresh ethane: published **1.331**, model **1.177 kg/kg**
- recycle ethane: published **0.601**, model **1.841 kg/kg**
- outlet C2H4: published **0.3995**, model **0.2541 mass fraction**
- OPEX: published **$195.65 M/y**, web screening value **$171.61 M/y**

The conversion target lies above the Aramco-GP thermal-history domain for this residence time. The paper uses a separate power-law kinetic model, a 502.77 °C reactor inlet, and 0.64 wt% ethylene in the reactor feed. These differences define the next kinetic benchmark.

## Reproduction

`benchmarks/index.html` loads the root app in a same-origin iframe and calls `window.ethaneModel.evaluate()`. The TEA equations therefore have one implementation.

`.github/workflows/literature-benchmarks.yml` opens the benchmark page in headless Chrome, extracts the machine-readable result, checks every test output, and writes `benchmarks/results.json`.
