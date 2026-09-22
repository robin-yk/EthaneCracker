#!/usr/bin/env python3
"""
Fit a compact shared-kernel Gaussian-process surrogate to a Cantera sweep.

Hyperparameters are selected against an internal tuning split, then the final GP
is refit on the full training sweep. An entirely separate Cantera sweep is used
by validate_surrogate.py for manuscript/release qualification.

All outputs share one anisotropic RBF kernel. This keeps the browser artifact
compact: one covariance inverse serves conversion, selectivity, species yields,
and heat. Holdout residuals from the internal tuning split calibrate the reported
posterior sigma separately for each output.
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
    "y_c2h6_kg_per_kg_ethane",
    "y_c3_kg_per_kg_ethane",
    "y_c4plus_kg_per_kg_ethane",
    "y_co_kg_per_kg_ethane",
    "y_co2_kg_per_kg_ethane",
    "heat_MJ_per_kg_ethane",
]


def load_csv(path: Path, outputs: list[str]) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise ValueError("dataset is empty")
    missing = [k for k in outputs if k not in rows[0]]
    if missing:
        raise ValueError("dataset missing outputs: " + ", ".join(missing))

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


def fit_gp(xn, yz, length, noise):
    k = rbf_kernel(xn, xn, length)
    k.flat[:: len(k) + 1] += noise
    l = np.linalg.cholesky(k)
    alpha = np.linalg.solve(l.T, np.linalg.solve(l, yz))
    eye = np.eye(len(k))
    linv = np.linalg.solve(l, eye)
    kinv = linv.T @ linv
    return alpha, kinv


def predict_gp(xtrain, xtest, alpha, kinv, length):
    k = rbf_kernel(xtest, xtrain, length)
    mean = k @ alpha
    # diag(Kxx - KxX K^-1 KXx); RBF amplitude is one.
    variance = 1.0 - np.einsum("ij,jk,ik->i", k, kinv, k)
    return mean, np.sqrt(np.maximum(variance, 0.0))


def score_candidate(ytrue, ypred):
    ranges = np.ptp(ytrue, axis=0)
    rmse = np.sqrt(np.mean((ypred - ytrue) ** 2, axis=0))
    useful = ranges > 1e-12
    if not np.any(useful):
        return float("inf"), rmse, ranges
    score = float(np.mean(rmse[useful] / ranges[useful]))
    return score, rmse, ranges


def domain_from_source(source, xmin, xmax):
    ranges = source.get("input_ranges") or {}
    if not ranges:
        return xmin.tolist(), xmax.tolist()
    lo = [
        ranges["temperature_c"][0],
        np.log10(ranges["residence_time_s"][0]),
        ranges["steam_hc_kgkg"][0],
        ranges["pressure_bar"][0],
        ranges["ramp_exponent"][0],
    ]
    hi = [
        ranges["temperature_c"][1],
        np.log10(ranges["residence_time_s"][1]),
        ranges["steam_hc_kgkg"][1],
        ranges["pressure_bar"][1],
        ranges["ramp_exponent"][1],
    ]
    return lo, hi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="multiscale/data/cantera_sweep.csv")
    ap.add_argument("--output", default="multiscale/surrogate.json")
    ap.add_argument("--report", default="multiscale/training_report.json")
    ap.add_argument(
        "--length-scale",
        default="0.22,0.20,0.28,0.30,0.28",
        help="base five RBF length scales after input normalization",
    )
    ap.add_argument(
        "--length-multipliers",
        default="0.5,0.75,1,1.35,1.75",
        help="global multipliers searched on an internal tuning split",
    )
    ap.add_argument("--noise", type=float, default=2e-6)
    ap.add_argument("--tune-fraction", type=float, default=0.20)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--outputs", default=",".join(DEFAULT_OUTPUTS))
    ap.add_argument("--round-digits", type=int, default=10)
    args = ap.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)
    outputs = [x.strip() for x in args.outputs.split(",") if x.strip()]
    base_length = np.array([float(x) for x in args.length_scale.split(",")], dtype=float)
    multipliers = [float(x) for x in args.length_multipliers.split(",")]
    if base_length.shape != (5,):
        raise ValueError("--length-scale needs five comma-separated values")

    x, y = load_csv(input_path, outputs)
    if len(x) < 32:
        raise ValueError("need at least 32 valid Cantera cases")

    xmin, xmax = x.min(axis=0), x.max(axis=0)
    span = np.maximum(xmax - xmin, 1e-12)
    xn = (x - xmin) / span
    ymean = y.mean(axis=0)
    ystd = y.std(axis=0)
    ystd[ystd < 1e-12] = 1.0
    yz = (y - ymean) / ystd

    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(x))
    ntune = max(8, int(round(len(x) * args.tune_fraction)))
    tune_idx = order[:ntune]
    fit_idx = order[ntune:]
    if len(fit_idx) < 16:
        raise ValueError("tuning split leaves too few fitting points")

    candidates = []
    best = None
    for mult in multipliers:
        length = base_length * mult
        alpha0, kinv0 = fit_gp(xn[fit_idx], yz[fit_idx], length, args.noise)
        pz, sig_std = predict_gp(xn[fit_idx], xn[tune_idx], alpha0, kinv0, length)
        pred = pz * ystd + ymean
        score, rmse, ranges = score_candidate(y[tune_idx], pred)
        item = {
            "multiplier": mult,
            "length_scale": length.tolist(),
            "mean_rmse_over_range": score,
        }
        candidates.append(item)
        if best is None or score < best["score"]:
            best = dict(
                score=score,
                multiplier=mult,
                length=length,
                pred=pred,
                sig_std=sig_std,
                alpha=alpha0,
                kinv=kinv0,
            )

    assert best is not None

    # Calibrate posterior sigma from tuning residuals. A floor of 0.25 prevents
    # unrealistically tiny intervals for outputs that happen to fit this split exactly.
    base_sigma = best["sig_std"][:, None] * ystd[None, :]
    residual = best["pred"] - y[tune_idx]
    ratio = residual / np.maximum(base_sigma, 1e-12)
    sigma_scale = np.sqrt(np.mean(ratio * ratio, axis=0))
    sigma_scale = np.clip(sigma_scale, 0.25, 20.0)

    # Refit the selected kernel on all training points for the deployable artifact.
    alpha, kinv = fit_gp(xn, yz, best["length"], args.noise)

    def arr(a):
        return np.round(np.asarray(a), args.round_digits).tolist()

    meta_path = input_path.with_suffix(".meta.json")
    source_meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    domain_min, domain_max = domain_from_source(source_meta, xmin, xmax)

    artifact = {
        "schema": "ethane-cantera-shared-rbf-gp-v2",
        "inputs": INPUTS,
        "outputs": outputs,
        "x_min": arr(xmin),
        "x_max": arr(xmax),
        "domain_min": arr(domain_min),
        "domain_max": arr(domain_max),
        "length_scale": arr(best["length"]),
        "noise": args.noise,
        "sigma_scale": arr(sigma_scale),
        "x_train": arr(xn),
        "alpha": arr(alpha),
        "k_inv": arr(kinv),
        "y_mean": arr(ymean),
        "y_std": arr(ystd),
        "training_points": int(len(x)),
        "source": source_meta,
        "notes": [
            "Residence time is transformed to log10(seconds) before normalization.",
            "Kernel length scale selected on an internal tuning split.",
            "Predictive sigma is empirically calibrated on that tuning split.",
            "Independent release validation uses a separately generated Cantera sweep.",
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")

    tune_metrics = {}
    for j, name in enumerate(outputs):
        e = best["pred"][:, j] - y[tune_idx, j]
        rmse = float(np.sqrt(np.mean(e * e)))
        mae = float(np.mean(np.abs(e)))
        yrange = float(np.ptp(y[tune_idx, j]))
        denom = float(np.sum((y[tune_idx, j] - y[tune_idx, j].mean()) ** 2))
        r2 = float(1 - np.sum(e * e) / denom) if denom > 0 else None
        calibrated = base_sigma[:, j] * sigma_scale[j]
        coverage = float(np.mean(np.abs(e) <= 1.96 * np.maximum(calibrated, 1e-15)))
        tune_metrics[name] = {
            "mae": mae,
            "rmse": rmse,
            "rmse_over_range": rmse / yrange if yrange > 0 else None,
            "r2": r2,
            "coverage_95": coverage,
            "sigma_scale": float(sigma_scale[j]),
        }

    report = {
        "schema": "ethane-cantera-gp-training-v2",
        "training_points": int(len(x)),
        "fit_points_internal": int(len(fit_idx)),
        "tuning_points_internal": int(len(tune_idx)),
        "seed": args.seed,
        "candidates": candidates,
        "selected_multiplier": best["multiplier"],
        "selected_length_scale": best["length"].tolist(),
        "internal_tuning_metrics": tune_metrics,
        "source": source_meta,
    }
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"trained final GP on {len(x)} cases; tuned on {len(tune_idx)} held-out internal cases")
    print(f"selected length multiplier {best['multiplier']} (score {best['score']:.5g})")
    for name, q in tune_metrics.items():
        print(
            f"  {name:30s} R2={q['r2']} RMSE/range={q['rmse_over_range']} "
            f"95%cov={q['coverage_95']:.3f}"
        )
    print(f"wrote {output_path} and {args.report}")


if __name__ == "__main__":
    main()
