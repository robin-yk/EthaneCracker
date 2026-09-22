# Cantera → GP reactor surrogate

This directory is the first mechanism-resolved reactor layer for the ethane-cracker TEA.

```
operating point
  T_out, residence time, steam/HC, pressure, heating-profile exponent
        │
        ▼
Cantera detailed chemistry sweep (offline)
        │
        ▼
shared-kernel Gaussian process
        │
        ▼
surrogate.json
        │
        ▼
browser inference (milliseconds)
        │
        ▼
ethane-cracker TEA / LCA
```

## What is implemented

- Latin-hypercube sampling over a five-dimensional reactor space.
- Cantera chemistry integration through a prescribed-temperature Lagrangian PFR approximation.
- A heating-profile parameter instead of a binary fired/Joule flag:
  `T(f) = Tin + (Tout - Tin) f^n`.
- Mechanism-derived ethane conversion, ethylene selectivity, major product yields, and required enthalpy rise.
- A zero-dependency shared-RBF Gaussian process with posterior uncertainty.
- JSON export that can be evaluated directly on GitHub Pages.
- A standalone browser demo in `demo.html`.

The browser never runs Cantera. Cantera is only needed when rebuilding the training data.

## Mechanism choice

The scripts default to Cantera's bundled `gri30.yaml` so a clean installation can smoke-test the pipeline. **That default is for software testing only.** Cantera's own documentation states that GRI-Mech is included for examples and is not recommended for research use. Replace it with a validated ethane-pyrolysis mechanism before interpreting chemical trends.

For AramcoMech, convert/download the mechanism as Cantera YAML and pass its gas-phase name:

```bash
python multiscale/cantera_sweep.py \
  --mechanism /path/to/aramcomech.yaml \
  --phase gas \
  --points 512 \
  --output multiscale/data/aramco_sweep.csv

python multiscale/train_gp.py \
  --input multiscale/data/aramco_sweep.csv \
  --output multiscale/surrogate.json
```

If the phase name differs, use the name defined by that YAML.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r multiscale/requirements.txt
```

## First smoke test

```bash
python multiscale/cantera_sweep.py --points 64
python multiscale/train_gp.py
python -m http.server 8000
```

Then open `http://localhost:8000/multiscale/demo.html`.

For a research sweep, start around 256–512 points, inspect holdout error, then add points where GP uncertainty is large. Exact GP training scales cubically with the number of training points, so thousands of raw Cantera cases should be down-selected or handled with a sparse GP in a later version.

## Current five-dimensional domain

| input | range |
|---|---:|
| outlet temperature | 750–1000 °C |
| residence time | 0.02–1.0 s, log sampled |
| steam / hydrocarbon | 0–0.70 kg/kg |
| pressure | 1–5 bar |
| heating-ramp exponent | 0.45–4 |

The inlet temperature defaults to 650 °C. The heating-ramp exponent changes how quickly the prescribed temperature approaches the outlet temperature. This lets fired and rapid internal-heating histories occupy one continuous model space.

## Outputs

The initial surrogate contains:

- ethane conversion
- ethylene molar selectivity
- ethylene, methane, hydrogen, acetylene and propylene mass yields
- external enthalpy rise required by the prescribed thermal history

Carbon, hydrogen and oxygen residuals are retained in the raw sweep for quality control.

## Boundary of v1

This is a homogeneous chemistry/PFR layer. It does not yet resolve radial temperature gradients, tube-wall radiation, pressure drop, coke deposition, or coupled solid electrical heating. Those belong in the next reactor-fidelity layer.

The immediate integration target in the root TEA is to replace the current first-order conversion and empirical selectivity correlation with GP outputs while keeping the existing separation, CAPEX/OPEX and LCA calculations.
