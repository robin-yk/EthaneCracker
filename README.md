# Mechanism-resolved techno-economics of an ethane cracker

Interactive screening model linking reactor operating conditions to detailed gas-phase chemistry, recycle and coproduct flows, separation loads, techno-economics, and carbon intensity.

The browser supports two reactor descriptions: (1) an empirical baseline retained for transparency and regression, and (2) AramcoMech 3.0 → Cantera → Gaussian-process chemistry for mechanism-resolved screening.

## Model chain

Operating point (outlet temperature, residence time, steam/HC, pressure, heating history) → AramcoMech 3.0 → Cantera prescribed-temperature PFR sweep → anisotropic GP surrogate → conversion/species yields/enthalpy → recycle and coproduct flows → separation loads → CAPEX/OPEX/carbon.

The browser evaluates the stored GP. Cantera runs offline when the training design space is rebuilt.

## Web interface

The root index.html contains the process/TEA/LCA interface. When a qualified surrogate is present, Aramco GP becomes available under Reactor model. Mechanism mode exposes reactor pressure and a continuous heating-history exponent with T(f)=Tin+(Tout−Tin)f^n.

The mechanism page at multiscale/demo.html reports model provenance, GP uncertainty, and independent Cantera holdout metrics.

## Mechanism-to-process coupling

For each reactor point, Cantera provides ethane conversion, ethylene selectivity, ethylene/methane/hydrogen/acetylene yields, unconverted ethane, C3 and C4+ lump yields, and the enthalpy rise over the prescribed thermal history.

The plant model scales those yields directly to one kilogram of ethylene. In mechanism mode, detailed chemistry controls fresh ethane demand, recycle, CH4/H2 fuel gas, acetylene and C3/C4+ loading, compressor/cold-box throughput, coproduct credit, reactor enthalpy demand, and downstream cost/carbon calculations.

Ethylene selectivity used by the plant model is derived from conversion and ethylene mass yield so conversion, yield, and selectivity cannot drift independently after GP interpolation.

## Validation and release gates

The GitHub Actions release gate performs:

- pinned Cantera installation;
- official AramcoMech 3.0 download and SHA-256 provenance capture;
- Chemkin-to-YAML conversion;
- reactor discretization-convergence checks;
- independent training and holdout Cantera sweeps using different sampling seeds;
- GP training with bounded output transforms;
- independent holdout R², normalized RMSE, and 95% interval coverage;
- elemental and total-mass closure checks on raw Cantera rows;
- JavaScript syntax and headless browser smoke tests;
- release-manifest generation with artifact hashes.

Generated training data, holdout data, surrogate, validation report, convergence report, and release manifest are committed only after the gates pass.

## Reproduce

1. Create a Python environment and install multiscale/requirements.txt.
2. Run: python multiscale/prepare_aramco.py --force-download
3. Generate training and independent holdout sweeps with multiscale/cantera_sweep.py.
4. Train multiscale/surrogate.json with multiscale/train_gp.py.
5. Evaluate the independent holdout with multiscale/validate_surrogate.py.
6. Serve the repository with python -m http.server 8000 and open the root page or multiscale/demo.html.

The workflow file .github/workflows/cantera-gp.yml contains the release configuration and numerical acceptance gates.

## Scientific boundary

This is a mechanism-to-process multiscale screening model. Detailed gas-phase chemistry is resolved offline, while the reactor uses a prescribed axial temperature history and homogeneous plug-flow approximation.

The present model does not resolve radial temperature gradients, furnace-side radiation, tube-wall conduction, pressure drop, coke-deposition kinetics, detailed quench chemistry, acetylene hydrogenation, or equipment-grade cryogenic separation. Downstream CAPEX/OPEX remains AACE Class 5 screening.

The defensible claim is that detailed reaction chemistry is propagated into process-level economic and environmental screening. The model does not support design-grade furnace, coil, cold-box, safety, or investment decisions.

## Mechanism provenance

AramcoMech 3.0 is retrieved from the University of Galway Combustion Chemistry Centre official distribution:

- Mechanism: https://www.universityofgalway.ie/media/researchcentres/combustionchemistrycentre/files/mechanismdownloads/aramcomech30/AramcoMech3.0.MECH
- Thermodynamics: https://www.universityofgalway.ie/media/researchcentres/combustionchemistrycentre/files/mechanismdownloads/aramcomech30/ARAMCOMECH30.THERM
- Transport: https://www.universityofgalway.ie/media/researchcentres/combustionchemistrycentre/files/mechanismdownloads/aramcomech30/AramcoMech3.0.TRAN

The converted YAML is generated during the reproducibility build and its SHA-256 digest is retained. Mechanism provenance alone does not establish ethane-pyrolysis accuracy; comparison against pyrolysis measurements in the target regime remains required for the strongest chemistry claim.

## Process reference

Mittal, A., Kwak, Y., Zheng, W., Ierapetritou, M., & Vlachos, D. G. (2025). Short contact time, high temperature, internally-heated ethane crackers. Chemical Engineering Journal, 523, 168251. https://doi.org/10.1016/j.cej.2025.168251

The mechanism-resolved model extends that process concept. Its detailed chemistry and GP surrogate are separate from the published Aspen-based TEA.

## Legacy reconstruction

ethane-cracker-tea-lab.html is a separate audit/reconstruction attempt of the published Aspen TEA. It is retained for provenance and is not the computational backend of the mechanism-resolved model. See TEA_tool_selfcheck.md.
