# Cantera sweep and GP surrogate

This directory generates the reactor-chemistry surrogate used by the root ethane-cracker TEA.

## Flow

```
T_out, residence time, steam/HC, pressure, heating exponent
        ↓
AramcoMech 3.0 + Cantera
        ↓
training and independent holdout sweeps
        ↓
Gaussian-process surrogate
        ↓
surrogate.json
        ↓
browser
        ↓
root TEA/LCA
```

The browser evaluates the stored surrogate. Cantera runs when the design space is generated.

## Files

- `prepare_aramco.py` downloads the official mechanism files, converts them with `ck2yaml`, and records hashes.
- `cantera_sweep.py` generates Latin-hypercube reactor calculations.
- `check_segment_convergence.py` compares reactor discretizations.
- `train_gp.py` fits the browser surrogate.
- `validate_surrogate.py` evaluates an independent Cantera holdout set.
- `gp_runtime.js` evaluates the stored GP in the browser.
- `demo.html` displays reactor outputs, provenance, uncertainty, and holdout metrics.
- `release_manifest.json` records hashes for generated release artifacts.

## Reactor domain

| input | range |
|---|---:|
| outlet temperature | 750–1000 °C |
| residence time | 0.02–1.5 s |
| steam / hydrocarbon | 0–0.70 kg/kg |
| pressure | 1–5 bar |
| heating-ramp exponent | 0.45–4 |

The inlet temperature is 650 °C.

[
T(f)=T_{in}+(T_{out}-T_{in})f^n
]

## Outputs

Each Cantera point stores conversion, ethylene selectivity, C2H4, C2H6, CH4, H2, C2H2, CO, CO2, C3, C4+, enthalpy rise, and C/H/O/mass residuals.

The root TEA scales the species yields from kg per kg coil ethane to kg per kg ethylene.

## Publication build

The current release configuration uses 640 training points (512 broad + 128 high-severity points), 128 independent holdout points, and 20 reactor segments.

Holdout metrics are stored in `validation.json`. Raw training and holdout datasets remain in `multiscale/data/`. The workflow regenerates all files from the official AramcoMech source distribution.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r multiscale/requirements.txt

python multiscale/prepare_aramco.py --force-download
```

Use `.github/workflows/cantera-gp.yml` as the exact reference for sweep, training, validation, and release commands.
