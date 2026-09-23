# Ethane cracker: AramcoMech/Cantera reactor chemistry with screening TEA

This repository calculates ethane-cracker economics and carbon intensity from reactor operating conditions. The default web model uses AramcoMech 3.0 chemistry solved with Cantera, compressed into a Gaussian-process surrogate, and passed into the existing process, TEA, LCA, sensitivity, and figure-generation code.

The original empirical reactor model remains available as **empirical baseline**. It uses the same downstream process model, cost basis, LCA inventory, and plotting code. Switching the reactor model therefore isolates the effect of reactor chemistry.

## Calculation chain

[
(T_{out},\tau,S/H,P,n)
\rightarrow
\text{reactor chemistry}
\rightarrow
\text{species yields and enthalpy}
\rightarrow
\text{recycle and separation loads}
\rightarrow
\text{CAPEX/OPEX}
\rightarrow
\text{cost and carbon}
]

For the Aramco GP route, Cantera supplies ethane conversion, ethylene selectivity, C2H4, C2H6, CH4, H2, C2H2, C3 and C4+ yields, and reactor enthalpy rise. The plant model converts those outputs to fresh ethane demand, recycle, tail-gas fuel, compressor load, refrigeration load, coproduct flow, heating duty, cost of ethylene, and carbon intensity.

The browser starts in Aramco GP mode after the stored surrogate passes its provenance and validation checks. The public workspace exposes the Aramco GP reactor model; the older empirical correlation remains only inside the calculation engine for regression checks.

## Current web model

The root `index.html` contains:

- fired and Joule heating cases;
- coil outlet temperature, residence time, steam dilution, pressure, and heating-history controls;
- ethane recycle;
- four-stage compression;
- AC-201 selective acetylene hydrogenation;
- cryogenic light-gas removal;
- C2 splitter shortcut calculations;
- TLE heat recovery;
- capacity-scaled CAPEX;
- OPEX and cost of ethylene;
- cradle-to-gate carbon intensity;
- fired/Joule power-price and grid-carbon crossovers;
- sensitivity analysis;
- baseline pinning and delta reporting;
- journal-size SVG and 600 dpi PNG export.

`multiscale/demo.html` isolates the reactor surrogate and reports mechanism provenance, GP uncertainty, and independent Cantera holdout metrics.

## AramcoMech / Cantera build

The GitHub Actions release workflow performs the full reactor build:

1. install pinned Cantera and NumPy versions;
2. download the official AramcoMech 3.0 Chemkin, thermodynamic, and transport files from the University of Galway;
3. record SHA-256 hashes;
4. convert the mechanism with Cantera `ck2yaml`;
5. check reactor-segment convergence;
6. generate independent training and holdout Latin-hypercube sweeps;
7. train the Gaussian-process surrogate;
8. evaluate the holdout set;
9. check C/H/O and mass closure for every Cantera point;
10. run JavaScript and headless-browser tests;
11. write a release manifest with artifact hashes.

The current publication build uses **640 training points, 128 independent holdout points, and 20 reactor segments**.

## Independent holdout results

| quantity | R² | RMSE / observed range |
|---|---:|---:|
| C2H6 conversion | 0.9997 | 0.0059 |
| C2H4 selectivity | 0.9993 | 0.0039 |
| C2H4 yield | 0.9994 | 0.0085 |
| CH4 yield | 0.9996 | 0.0026 |
| H2 yield | 0.9995 | 0.0076 |
| C2H2 yield | 0.9956 | 0.0124 |
| C3 lump | 0.9971 | 0.0162 |
| C4+ lump | 0.9962 | 0.0098 |
| enthalpy rise | 0.9993 | 0.0077 |

These values compare GP predictions with a Cantera holdout design generated from a separate Latin-hypercube seed.

## Reactor model

Cantera advances a reacting fluid element through a prescribed temperature history,

[
T(f)=T_{in}+(T_{out}-T_{in})f^n,
]

with (f=t/\tau). The current design space is:

| input | range |
|---|---:|
| outlet temperature | 750–1000 °C |
| residence time | 0.02–1.5 s |
| steam / hydrocarbon | 0–0.70 kg/kg |
| pressure | 1–5 bar |
| heating-ramp exponent | 0.45–4 |
| inlet temperature | 650 °C |

The heating exponent describes the imposed thermal history. Reactor-specific values require temperature histories from experiment or a higher-fidelity heat-transfer model.

## Mechanism-to-process transformation

Cantera yields use kg species per kg ethane entering the coil. AC-201 recovers part of the reactor acetylene as ethylene before the plant is scaled to one kg of final ethylene product. If (f_{AC}) is the acetylene conversion in AC-201 and (S_{AC}) is its selectivity to ethylene,

[
Y_{C2H4,AC}=Y_{C2H2}\,f_{AC}\,S_{AC}\frac{MW_{C2H4}}{MW_{C2H2}},
]

[
Y_{C2H4,final}=Y_{C2H4}+Y_{C2H4,AC},
]

[
m_{coil,C2H6}=\frac{1}{Y_{C2H4,final}}.
]

The ethane formed by over-hydrogenation is

[
Y_{C2H6,AC}=Y_{C2H2}\,f_{AC}(1-S_{AC})\frac{MW_{C2H6}}{MW_{C2H2}},
]

and the fresh-feed/recycle screening balances are

[
m_{fresh,C2H6}=(X-Y_{C2H6,AC})m_{coil,C2H6},
]

[
m_{recycle,C2H6}=(1-X+Y_{C2H6,AC})m_{coil,C2H6}.
]

CH4 and H2 set the cracked-gas fuel inventory. C2H2 is compressed with the cracked gas and then passes through AC-201 before the cold box. The screening converter targets 5 ppm residual acetylene and assigns 90% of converted acetylene to ethylene; the balance forms ethane. Hydrogen is taken from the mechanism-predicted H2 stream before the remaining H2 enters the tail gas. C3, C4+, and unconverted C2H6 continue into the downstream flow calculations. Cantera enthalpy supplies the 650 °C-to-outlet reactor duty; the process model supplies upstream preheat and TLE recovery.

## Numerical checks

The publication workflow compares 20 and 40 reactor segments at five operating points. The 20-segment calculation stays within the declared convergence thresholds.

Every raw Cantera training and holdout point records carbon, hydrogen, oxygen, and mass residuals. The workflow rejects a dataset if any absolute residual exceeds (10^{-8}).

The browser stores the maximum raw Cantera closure residuals in the surrogate metadata and displays them in the balances figure.

## Process and TEA scope

The process layer uses screening correlations for AC-201, the cold box, C2 splitter, capital scaling, and utility costs. Capital is reported as AACE Class 5.

AC-201 is a front-end screening block placed after compression and before the cold box. It converts acetylene to a 5 ppm target using mechanism-predicted H2. The default ethylene selectivity is 90%; the remainder forms ethane and returns with the recycle. The converter vessel is treated as part of the existing recovery-section capital anchor, so no separate converter CAPEX is added.

Current equations cover reactor chemistry, acetylene conversion, recycle, compression, refrigeration screening, C2 fractionation screening, TLE recovery, coproduct credits, cost, and LCA.

Higher-fidelity extensions require radial reactor temperature gradients, furnace-side radiation, tube-wall conduction, pressure drop, coke-deposition kinetics, detailed quench chemistry, a kinetic acetylene-converter model with green-oil/catalyst-aging behavior, rigorous multicomponent cryogenic thermodynamics, and vendor equipment design.

## Experimental chemistry benchmark

The GP validation above measures surrogate error relative to Cantera. Experimental mechanism fidelity is a separate validation layer.

A directly relevant dataset is:

S. J. Cassady, R. Choudhary, N. H. Pinkowski, J. Shao, D. F. Davidson, R. K. Hanson, “The thermal decomposition of ethane,” *Fuel* **268** (2020) 117409. DOI: 10.1016/j.fuel.2020.117409.

The study reports C2H6, C2H4, CH4, and C2H2 time histories for 1–2% ethane in Ar over 1178–1527 K and 3.1–4.2 atm. The manuscript validation plan uses those measurements as the external kinetic benchmark.

## Process reference

Mittal, A., Kwak, Y., Zheng, W., Ierapetritou, M., & Vlachos, D. G. (2025). “Short contact time, high temperature, internally-heated ethane crackers.” *Chemical Engineering Journal* **523**, 168251. DOI: 10.1016/j.cej.2025.168251.

The Aramco GP and empirical baseline share the downstream TEA so reactor-model effects can be compared on the same process and economic basis.

## Reproduce

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r multiscale/requirements.txt

python multiscale/prepare_aramco.py --force-download
# Exact sweep, training, validation, and release commands:
# .github/workflows/cantera-gp.yml

python -m http.server 8000
```

Open `http://localhost:8000/`.
<!-- publication GP rebuild: expanded tau domain, 512 broad + 128 targeted + 128 holdout -->

## Literature-constrained TEA uncertainty

`uncertainty/` contains a separate research analysis that calibrates effective fired efficiency and compression duty against the documented literature utility observations, retains uncalibrated heat-recovery/capital assumptions, and propagates shared parameter draws into paired fired/Joule costs and break-even electricity prices. The Model page links to its dashboard. See [method, source boundaries and reproduction](uncertainty/README.md). These are conditional scenario results; same-study held-out outputs and unresolved mismatches remain visible.
