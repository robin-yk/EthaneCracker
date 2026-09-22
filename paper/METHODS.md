# Mechanism-resolved multiscale ethane cracker — methods and claim boundary

## Scientific claim

The web model links five computational layers:

1. **elementary chemistry** — detailed gas-phase kinetics from AramcoMech 3.0;
2. **reactor history** — a constant-pressure Lagrangian PFR approximation with a prescribed axial/time temperature history;
3. **surrogate layer** — a Gaussian process trained on Cantera calculations and evaluated in the browser;
4. **process layer** — recycle, compression, cryogenic separation, fractionation, and heat recovery;
5. **plant layer** — screening CAPEX/OPEX and cradle-to-gate carbon intensity.

The intended claim is **mechanism-resolved early-stage process screening**. The model is not a furnace CFD model, a design-grade ethylene-plant simulator, or an investment-grade cost estimate.

## 1. Detailed chemical mechanism

AramcoMech 3.0 is obtained at build time from the University of Galway Combustion Chemistry Centre official mechanism-download page. The Chemkin mechanism, thermodynamic data, and transport data are converted with Cantera `ck2yaml`. The build records:

- source URLs;
- SHA-256 digests of the three downloaded source files;
- SHA-256 of the converted YAML;
- Cantera version;
- number of species and reactions;
- Git commit used for the sweep.

Primary mechanism reference:

C.-W. Zhou et al., *Combustion and Flame* **197** (2018) 423–438. DOI: 10.1016/j.combustflame.2018.08.006.

A mechanism SHA is part of every generated sweep metadata file. A changed upstream mechanism therefore produces a changed provenance record even when the filename is unchanged.

## 2. Reactor model

The chemistry calculation uses a Lagrangian approximation to a plug-flow reactor. A reacting fluid element is integrated through a sequence of constant-pressure, isothermal Cantera reactor segments. The imposed temperature trajectory is

\[
T(f)=T_{in}+(T_{out}-T_{in})f^n,
\]

where \(f=t/\tau\), \(0\le f\le1\), \(\tau\) is residence time, and \(n\) is a heating-ramp exponent.

The initial screening domain is:

| variable | domain |
|---|---:|
| outlet temperature | 750–1000 °C |
| residence time | 0.02–1.0 s, log sampled |
| steam / hydrocarbon | 0–0.70 kg kg⁻¹ |
| pressure | 1–5 bar |
| heating-ramp exponent | 0.45–4 |
| inlet temperature | 650 °C, fixed in v1 |

The ramp exponent is a compact descriptor of thermal history. It is not by itself identified with a fired or electrically heated reactor. Reactor-specific thermal histories must be calibrated against measured or simulated temperature profiles before claims about heating architecture are made.

## 3. Cantera outputs and plant-scale transformation

Every Cantera point reports:

- ethane conversion;
- molar ethylene selectivity;
- ethylene, ethane, methane, hydrogen, acetylene, CO and CO₂ mass yields;
- total C3 mass lump;
- total C4+ mass lump;
- external enthalpy rise;
- carbon, hydrogen, oxygen, and total-mass residuals.

Species yields use kg species per kg ethane entering the coil.

For ideal recovery of unreacted ethane, the per-kg-ethylene reactor flows are obtained directly from the mechanism-derived ethylene yield \(Y_{C2H4}\):

\[
m_{coil,C2H6} = \frac{1}{Y_{C2H4}},
\]

\[
m_{recycle,C2H6} = \frac{1-X}{Y_{C2H4}},
\]

\[
m_{fresh,C2H6} = \frac{X}{Y_{C2H4}}.
\]

This removes the empirical byproduct partition used in the original screening model from the mechanism-resolved route.

## 4. Design-space sampling

Training and external holdout points are generated as independent Latin-hypercube designs with different random seeds. Residence time is sampled uniformly in log₁₀ space; the other variables are sampled uniformly over their declared domains.

The training and holdout files are retained in the repository together with metadata. Elemental closure is a release gate. The current CI threshold is an absolute residual below 10⁻⁸ for C, H, O, and total mass at every generated point.

## 5. Gaussian-process surrogate

Inputs are

\[
[T_{out},\log_{10}\tau,S/H,P,n].
\]

Each input is normalized to the span of the training set. All outputs share one anisotropic radial-basis-function kernel,

\[
k(\mathbf x,\mathbf x')
=
\exp\left[
-\frac12
\sum_j\left(\frac{x_j-x'_j}{\ell_j}\right)^2
\right].
\]

The base length-scale vector is multiplied by several candidate global factors. The factor minimizing mean output RMSE normalized by the observed tuning-set range is selected using an internal tuning split. After selection, the GP is refit on the complete training sweep.

Posterior uncertainty is calibrated against residuals from the internal tuning split separately for each output. Browser inference exports the training coordinates, GP coefficients, covariance inverse, normalization parameters, and uncertainty calibration factors to a static JSON artifact. No Cantera calculation is performed in the browser.

## 6. Three separate validation tiers

### Tier A — conservation

Every Cantera point must satisfy elemental and total-mass closure below the release threshold.

### Tier B — surrogate fidelity

A second Cantera Latin-hypercube sweep is never used in GP fitting or hyperparameter selection. The release report gives, for every output:

- MAE;
- RMSE;
- maximum absolute error;
- R²;
- RMSE divided by observed output range;
- empirical coverage of the calibrated 95% GP interval.

This tier answers: *does the browser surrogate reproduce Cantera within the declared design space?*

### Tier C — chemical-mechanism fidelity

A separate external benchmark must compare AramcoMech predictions with experimental ethane-pyrolysis measurements. The primary target is:

S. J. Cassady, R. Choudhary, N. H. Pinkowski, J. Shao, D. F. Davidson, R. K. Hanson, “The thermal decomposition of ethane,” *Fuel* **268** (2020) 117409. DOI: 10.1016/j.fuel.2020.117409.

That study reports time histories for ethane, ethylene, methane, and acetylene during 1% and 2% ethane pyrolysis in Ar at 1178–1527 K and 3.1–4.2 atm. Tier C is distinct from GP validation: a surrogate can perfectly reproduce a chemically inaccurate mechanism.

## 7. Browser guardrails

The browser returns the raw GP mean and calibrated sigma. It does not silently truncate values to physically allowed ranges.

A result is marked unqualified when:

- any input lies outside the declared design domain;
- conversion or selectivity falls outside [0,1];
- a predicted species mass yield is negative beyond numerical tolerance;
- any required result is non-finite.

The UI exposes mechanism identity, mechanism size, SHA-256, Cantera version, number of training points, and independent holdout metrics.

## 8. Process / TEA boundary

The downstream process model remains screening-level. Cryogenic separation and fractionation use shortcut relationships, and equipment costs remain correlation-based. The economic output must therefore retain its AACE Class 5 framing.

The mechanism-resolved reactor route materially improves the propagation of reactor chemistry into:

- fresh-feed requirement;
- recycle load;
- light-gas load;
- C3/C4+ coproduct production;
- reactor enthalpy demand;
- compression and refrigeration demand.

It does not provide vendor equipment sizing, furnace radiation, tube-wall stresses, detailed hydraulics, or rigorous multicomponent column design.

## 9. Remaining work before a manuscript-level release

The release is publishable only after all of the following are present in one tagged revision:

1. official AramcoMech provenance and reproducible Chemkin→YAML conversion;
2. sufficiently dense independent train/holdout sweeps;
3. pre-declared numerical acceptance criteria that the independent holdout passes;
4. Cassady et al. external kinetic validation;
5. mechanism-derived reactor inventory connected to the root TEA/LCA app;
6. side-by-side empirical vs mechanism-resolved comparison;
7. convergence study with respect to reactor segment count and sweep density;
8. figure/data export sufficient to reproduce every reported web-paper result from the tagged commit.

