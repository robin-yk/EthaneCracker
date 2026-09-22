#!/usr/bin/env python3
"""
Fit a compact shared-kernel Gaussian-process surrogate to a Cantera sweep.

All outputs share one RBF kernel and therefore one covariance inverse. This keeps
the browser artifact small while retaining exact GP interpolation for each
standardized output. The browser receives X_train, alpha, K^-1, input bounds,
output scaling, and metadata. Predictive variance is computed from the GP kernel,
not from a nearest-neighbor heuristic.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import numpy as np


INPUTS = [
    "temperature_c",
    "log10_residence_time_s",
    "steam_hc_kgkg",
    "pressure_bar",
    "ramp_exponent",
]

DEFAULT_OUTPUTS = [
    "x_c2h6",
    "s_c2h4_mol",
    "y_c2h4_kg_per_kg_ethane",
    "y_ch4_kg_per_kg_ethane",
    "y_h2_kg_per_kg_ethane",
    "y_c2h2_kg_per_kg_ethane",
    "y_c3h6_kg_per_kg_ethane",
    "heat_MJ_per_kg_ethane",
]


def load_csv(path: Path, outputs: list[str]) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise ValueError("dataset is empty")

    x = np.array(
        [
            [
                float(r["temperature_c"]),
                np.log10(float(r["residence_time_s"])),
                float(r["steam_hc_kgkg"]),
                float(r["pressure_bar"]),
                float(r["ramp_exponent"]),
            ]
            for r in rows
        ],
        dtype=float,
    )
    y = np.array([[float(r[k]) for k in outputs] for r in rows], dtype=float)

    good = np.isfinite(x).all(axis=1) & np.isfinite(y).all(axis=1)
    return x[good], y[good]


def rbf_kernel(xa: np.ndarray, xb: np.ndarray, length: np.ndarray) -> np.ndarray:
    d = (xa[:, None, :] - xb[None, :, :]) / length[None, None, :]
    return np.exp(-0.5 * np.sum(d * d, axis=2))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="multiscale/data/cantera_sweep.csv")
    ap.add_argument("--output", default="multiscale/surrogate.json")
    ap.add_argument(
        "--length-scale",
        default="0.22,0.20,0.28,0.30,0.28",
        help="five RBF length scales after input normalization",
    )
    ap.add_argument("--noise", type=float, default=2e-6)
    ap.add_argument("--outputs", default=",".join(DEFAULT_OUTPUTS))
    ap.add_argument("--round-digits", type=int, default=10)
    args = ap.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    outputs = [x.strip() for x in args.outputs.split(",") if x.strip()]
    length = np.array([float(x) for x in args.length_scale.split(",")], dtype=float)
    if length.shape != (5,):
        raise ValueError("--length-scale needs five comma-separated values")

    x, y = load_csv(input_path, outputs)
    if len(x) < 16:
        raise ValueError("need at least 16 valid Cantera cases")

    xmin, xmax = x.min(axis=0), x.max(axis=0)
    span = np.maximum(xmax - xmin, 1e-12)
    xn = (x - xmin) / span

    ymean = y.mean(axis=0)
    ystd = y.std(axis=0)
    ystd[ystd < 1e-12] = 1.0
    yz = (y - ymean) / ystd

    k = rbf_kernel(xn, xn, length)
    k.flat[:: len(k) + 1] += args.noise

    # Cholesky gives numerically stable alpha; K^-1 is exported once because the
    # shared kernel lets every output use the same predictive variance.
    l = np.linalg.cholesky(k)
    alpha = np.linalg.solve(l.T, np.linalg.solve(l, yz))
    eye = np.eye(len(k))
    linv = np.linalg.solve(l, eye)
    kinv = linv.T @ linv

    def arr(a):
        return np.round(np.asarray(a), args.round_digits).tolist()

    meta_path = input_path.with_suffix(".meta.json")
    source_meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}

    artifact = {
        "schema": "ethane-cantera-shared-rbf-gp-v1",
        "inputs": INPUTS,
        "outputs": outputs,
        "x_min": arr(xmin),
        "x_max": arr(xmax),
        "length_scale": arr(length),
        "noise": args.noise,
        "x_train": arr(xn),
        "alpha": arr(alpha),
        "k_inv": arr(kinv),
        "y_mean": arr(ymean),
        "y_std": arr(ystd),
        "training_points": int(len(x)),
        "source": source_meta,
        "notes": [
            "Residence time is transformed to log10(seconds) before normalization.",
            "Predictive sigma uses the shared standardized-output covariance.",
            "Research use requires a validated ethane-pyrolysis mechanism.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")

    # Training interpolation error is a useful sanity check for accidental damage.
    predz = k @ alpha
    pred = predz * ystd + ymean
    mae = np.mean(np.abs(pred - y), axis=0)
    print(f"trained on {len(x)} cases")
    for name, err in zip(outputs, mae):
        print(f"  {name:30s} train MAE {err:.6g}")
    print(f"wrote {output_path}")


if __name__ == "__main__":
    main()
