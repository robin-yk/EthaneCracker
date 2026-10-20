# Methods: reactor chemistry coupled to ethane-cracker TEA

## 1. Model architecture

The calculation contains five layers:

1. AramcoMech 3.0 gas-phase kinetics;
2. a prescribed-temperature plug-flow reactor calculation in Cantera;
3. a Gaussian-process surrogate for browser evaluation;
4. an ethane-cracker process model for recycle, compression, refrigeration, fractionation, and heat recovery;
5. screening TEA and LCA.

The web app loads the Aramco GP as its default reactor description after provenance and holdout checks pass. The empirical reactor model remains available as a baseline and feeds the same process model.

## 2. Chemical mechanism

The release workflow downloads AramcoMech 3.0 from the University of Galway Combustion Chemistry Centre. The build retrieves the Chemkin mechanism, thermodynamic data, and transport data, then converts them with Cantera `ck2yaml`.

The provenance record stores:

- source URLs;
- SHA-256 for each downloaded source file;
- SHA-256 for the converted YAML;
- Cantera version;
- gas-phase species count;
- reaction count;
- Git commit SHA used for the sweep.

Primary mechanism reference:

C.-W. Zhou et al., *Combustion and Flame* **197** (2018) 423–438. DOI: 10.1016/j.combustflame.2018.08.006.

## 3. Reactor calculation

A Lagrangian fluid element advances through a constant-pressure reactor network with the imposed thermal history

[
T(f)=T_{in}+(T_{out}-T_{in})f^n,
]

where (f=t/\tau), (	au) is residence time, and (n) is the heating-ramp exponent.

The current domain is:

| variable | range |
|---|---:|
| outlet temperature | 750–1000 °C |
| residence time | 0.02–1.5 s |
| steam / hydrocarbon | 0–0.70 kg kg⁻¹ |
| pressure | 1–5 bar |
| heating-ramp exponent | 0.45–4 |
| inlet temperature | 650 °C |

Residence time is sampled uniformly in log10 space. The other four variable dimensions use uniform Latin-hypercube coordinates.

Segment boundaries are uniform in normalized temperature progress. This places more integration intervals where the prescribed temperature curve changes fastest.

## 4. Segment-convergence check

The release workflow evaluates five reactor conditions with 20 and 40 segments. Acceptance thresholds are:

- conversion absolute difference ≤ 0.005;
- ethylene selectivity absolute difference ≤ 0.005;
- ethylene yield absolute difference ≤ 0.005 kg kg⁻¹;
- enthalpy relative difference ≤ 0.01.

The publication build passed all five cases. At the 850 °C, 0.35 s baseline, the 20-to-40 segment differences were approximately (8.8\times10^{-4}) in conversion, (5.8\times10^{-5}) in molar ethylene selectivity, (7.5\times10^{-4}) kg kg⁻¹ in ethylene yield, and 0.15% in enthalpy.

## 5. Cantera outputs

Each reactor point stores:

- ethane conversion;
- molar ethylene selectivity;
- C2H4, C2H6, CH4, H2, C2H2, CO, and CO2 mass yields;
- total C3 mass yield;
- total C4+ mass yield;
- enthalpy rise;
- carbon, hydrogen, oxygen, and total-mass residuals.

Species yields use kg species per kg ethane entering the coil.

C3 and C4+ are mass lumps formed by summing all mechanism species with three carbon atoms and four-or-more carbon atoms, respectively.

## 6. Plant-scale transformation

The basis is one kg of recovered ethylene. Cold-box ethylene recovery is `R = 0.995`; unconverted ethane is recycled. Let `Y_E` be reactor ethylene yield, `ΔY_E` ethylene formed in AC-201, and `ΔY_ethane` ethane formed in AC-201, each per kg coil ethane:

- `m_coil = 1 / [R × (Y_E + ΔY_E)]`
- `m_fresh = (X − ΔY_ethane) × m_coil`
- `m_recycle = m_coil − m_fresh`
- `m_ethylene,tail = 1/R − 1`

The same coil scale converts each reactor species yield to kg per kg recovered ethylene. The 0.5% unrecovered ethylene joins the light tail gas; its heating value and combustion carbon follow that stream.

The process model uses those flows in the tail-gas balance, compressor flow, cold-box screening calculation, and coproduct credit.

Cantera reports enthalpy rise from 650 °C to the selected outlet condition. The process model calculates preheat from 150 to 650 °C and combines both terms for the reactor heating requirement.

## 7. Gaussian-process surrogate

The GP input vector is

[
[T_{out},\log_{10}\tau,S/H,P,n].
]

Inputs are normalized with the training-set bounds.

Conversion and selectivity use logit transforms. Non-negative yields and enthalpy use logarithmic transforms. These transforms place bounded and multi-decade outputs on smoother latent scales before fitting.

All outputs share an anisotropic radial-basis-function covariance,

[
k(\mathbf{x},\mathbf{x}')
=
\exp\left[
-\frac{1}{2}
\sum_j
\left(
\frac{x_j-x'_j}{\ell_j}
\right)^2
\right].
]

A deterministic candidate search selects the length-scale vector using an internal tuning subset. The model is then refit on the full training sweep.

The browser artifact stores normalized training coordinates, GP coefficients, covariance inverse, output transforms, output scales, input domain, and provenance metadata.

## 8. Training and external holdout

The publication build uses:

- 640 training points: 512 broad-domain and 128 high-severity points, with seed 42;
- 128 holdout points with seed 4242;
- 20 reactor segments.

The holdout points remain outside GP fitting and hyperparameter selection.

Release acceptance requires R² ≥ 0.90 and RMSE/observed range ≤ 0.08 for the designated outputs.

The current holdout results are:

| quantity | R² | RMSE / range |
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

The validation artifact also stores MAE, RMSE, maximum absolute error, prediction range, and calibrated 95% interval coverage.

## 9. Conservation checks

Every raw Cantera row records carbon, hydrogen, oxygen, and total-mass residuals. The release gate requires each absolute residual to stay below (10^{-8}).

The sweep metadata stores the maximum absolute residual for each quantity. The web balances figure reads those maxima in Aramco GP mode.

The empirical baseline retains its original algebraic C/H/mass/energy residual calculation.

## 10. Process model

The downstream model uses the same equations for both reactor descriptions.

Compression uses a four-stage ideal-gas shortcut to 32 bar. The compressed cracked gas then passes through a screening acetylene converter before cryogenic separation. This placement represents a front-end hydrogenation arrangement within the reduced process flowsheet. EPA ethylene-process descriptions place selective acetylene hydrogenation upstream of the ethylene/ethane splitter and report polymer-grade acetylene specifications of roughly 5–10 ppm; the present screening model uses a 5 ppm product target, conservatively assigning all residual acetylene to recovered ethylene. Converter-outlet C2 ppm is reported separately.

Converted acetylene is assigned 90% selectivity to ethylene and 10% to ethane. The 90% selectivity is a fixed input based on reported Pd acetylene hydrogenation. Hydrogen is withdrawn from the mechanism-predicted H2 stream. The 640-point Cantera training design contains more H2 than this stoichiometric requirement at every point. The converter is included within the existing recovery-section capital anchor and does not receive a separate vessel CAPEX in this screening model.

Process references for this block are the U.S. EPA *Industrial Process Profiles for Environmental Use: Chapter 5 — Basic Petrochemical Industry*, Olefins Production Process No. 8, and the palladium acetylene-hydrogenation study reporting ethylene selectivity around 90% (DOI: 10.1016/0304-5102(93)E0323-9).

The web interface also reports a bed-count severity indicator from the raw C2 acetylene concentration: one bed below 0.5 mol%, two beds from 0.5 to 1.7 mol%, and three beds above 1.7 mol%. This follows published tail-end reactor practice and is displayed as a design indicator only; bed count does not independently scale CAPEX in the present screening TEA.

The cold box is solved in the engine with the Peng–Robinson equation of state (ChemSep binary interaction parameters; NASA polynomials for the ideal-gas enthalpy). A flash at 30 bar gives the cold-end temperature that leaves 0.5 % of the ethylene in the tail gas. The refrigeration duty at the −40 °C, −100 °C and cold-end levels is the feed enthalpy drop between the level boundaries less the enthalpy taken up by the tail gas and the condensate rewarming against the feed with a 5 K approach, walked in 10 K steps so that no step recuperates more than the feed releases. A propylene / ethylene / methane cascade of two-stage vapor-compression cycles evaluated with CoolProp converts duty to work (COP 1.69, 1.45, 2.88; isentropic efficiency 0.75; `multiscale/coldbox/refrigeration_cycles.py`). The C2-splitter condenser at −30 °C sits on the propylene cycle (COP 2.07). The engine's flash and enthalpy balance agree with the thermo-library calculation on 1,232 feed compositions within 0.04 K and 1.3 % of refrigeration work (`multiscale/coldbox/check_engine.cjs`). The C2 splitter uses Fenske–Underwood–Gilliland-style shortcut relationships at fixed product purity and recovery.

Heavy ends (added 2026-10-20). C5+ condenses in the quench tower and the compressor interstage drums and leaves before the cold box; the compressor still carries it. The cold-box liquid goes to a deethanizer at 25 bar whose overhead feeds the C2 splitter. The deethanizer bottoms (C3 + C4) go to a depropanizer at 16 bar (C3 overhead), and its bottoms with the quench C5+ go to a debutanizer at 5 bar (C4 overhead, raw pyrolysis-gasoline bottoms). Each column is a Fenske–Underwood–Gilliland shortcut solved at the operating point's flows: keys recovered 99.5 %, reflux 1.2 times the Underwood minimum, stages from the Eduljee form of the Gilliland correlation, tray efficiency 0.7. Relative volatilities, latent heats and top densities are Peng–Robinson values at the reference composition. The deethanizer condenser (−8 °C) uses a two-stage propylene cycle (COP 3.49); the other condensers use cooling water. Reboiler duty is the condenser duty plus the bottoms sensible heat and is charged as low-pressure steam at the export-steam price, with the boiler emission factor. The GP's C4+ lump is split into C4 and C5+ with a fit to 225 direct Cantera calculations, f = 1 − exp[−(y/0.1122)^1.026] with y the C4+ yield per kg coil ethane; direct Cantera rows use their own split. Column diameter follows the Souders–Brown form of Towler and Sinnott (2022, Eq. 17.47), shell thickness the ASME relation (Eq. 14.13), and purchased cost Table 7.2 with Hand installation factors. Because the anchor plant already contains a C2/C3 column, the deethanizer adds capital only for its size difference from the reference case; Towler costs are converted to the anchor basis with the ratio of the anchor fractionation share to the Towler cost of the reference C2 splitter and deethanizer (0.261). Product prices are unchanged: C3, C4 and C5+ are credited at the C3+ price unless the user changes it.

TLE recovery credits recovered sensible heat. Tail gas supplies fired-heater demand before purchased natural gas. The Joule case supplies reactor heat electrically and consumes no tail gas in the heater. Surplus tail gas follows the selected burn, sell, or vent route; only sold gas earns revenue and displacement credit. Mass allocation uses the sold surplus mass. Methane venting uses the existing fossil-methane GWP; ethylene vent mass is retained in the inventory without a separate GWP factor. Sold surplus gas is hydrogen-rich, off-specification fuel; it is valued at the tail-gas price, by default half the natural-gas price per GJ (LHV), and in the carbon account it displaces natural gas. The export-steam price defaults to the natural-gas price divided by a 0.90 boiler efficiency (4.4 USD/GJ at 4 USD/GJ gas), the fuel-based steam price of Towler and Sinnott (Chemical Engineering Design, 2nd ed., Eq. 3.1).

The capital model starts from the published 610 kt y⁻¹ bare-module anchor and applies section-specific capacity scaling. Total overnight cost uses the existing TOC/TBMC factor. OPEX combines feedstock, utilities, credits, capital charge, maintenance, and labor.

## 11. LCA

The LCA reads the same process inventory used by the cost model.

Scope 1 includes purchased gas, tail-gas combustion, and the empirical decoking term where present. Scope 2 uses purchased electricity and the selected grid factor. Scope 3 uses the upstream ethane factor.

TLE steam and C3+ coproducts enter the selected coproduct treatment. The C3+ screening lump uses the same price and displacement-factor basis already used by the TEA.

## 12. Fired and Joule comparison

The fired and Joule cases share the reactor chemistry model. The heating mode changes efficiency, energy source, and the declared accessible temperature/residence-time envelope.

The current fired envelope spans 760–900 °C with residence time ≥0.20 s. The Joule envelope spans 760–950 °C with residence time ≥0.05 s.

These envelopes are screening inputs. Reactor-specific thermal histories require measured or simulated profiles. The heating-ramp exponent supplies a continuous thermal-history coordinate for that future calibration.

## 13. Experimental kinetic benchmark

Surrogate holdout validation measures GP fidelity to Cantera.

The planned experimental comparison uses the following ethane-pyrolysis dataset:

S. J. Cassady, R. Choudhary, N. H. Pinkowski, J. Shao, D. F. Davidson, R. K. Hanson, “The thermal decomposition of ethane,” *Fuel* **268** (2020) 117409. DOI: 10.1016/j.fuel.2020.117409.

The study reports time histories for ethane, ethylene, methane, and acetylene during 1% and 2% ethane pyrolysis in Ar over 1178–1527 K and 3.1–4.2 atm.

Current release status:

- raw Cantera conservation: complete;
- reactor segment convergence: complete;
- independent GP holdout: complete;
- browser integration and headless test: complete;
- Cassady et al. experimental comparison: pending.

## 14. Model scope

The current calculation covers gas-phase chemistry, imposed thermal history, recycle, compression, screening acetylene hydrogenation, refrigeration from an equation-of-state flash and cascade, C2 fractionation screening, heat recovery, CAPEX/OPEX, and LCA.

Higher-fidelity reactor work requires radial temperature gradients, furnace-side radiation, tube-wall conduction, pressure drop, and coke-deposition kinetics.

Higher-fidelity downstream work requires rigorous multicomponent thermodynamics, detailed quench chemistry, acetylene-hydrogenation kinetics including catalyst deactivation and green-oil formation, and vendor equipment design.

Economic results retain the AACE Class 5 screening classification.

## 15. TEA uncertainty

Literature-based effective parameter estimates and paired cost uncertainty are calculated using bounded quadrature and shared parameter draws. The calculation covers three discrepancy scales, three Joule efficiencies, and three furnace capital factors. See [parameter estimates and economic intervals](UNCERTAINTY.md) and [equations and input ranges](../uncertainty/README.md).
