#!/usr/bin/env python3
"""
Train the browser surrogate for the mechanism-resolved ethane cracker.

The GP works in transformed output space:
- conversion / selectivity: logit transform;
- non-negative yields and enthalpy: log(y + epsilon).

Those transforms remove hard [0,1] boundaries and several-order-of-magnitude
curvature before fitting. One anisotropic RBF covariance is shared across outputs
so the static browser artifact remains compact. Five independent length scales
are selected from deterministic candidate search on an internal tuning split.
An entirely separate Cantera sweep is reserved for release validation.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np


INPUTS = [
    "temperature_c",
    "log10_residence_time_s",
    "steam_hc_kgkg",
    "pressure_bar",
    "ramp_exponent",
]

# CO / CO2 remain in the raw Cantera dataset for chemistry diagnostics. They are
# trace products in this oxygen-free screening domain and are not used by the
# downstream cracker model, so v2 does not claim a browser surrogate for them.
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
    "heat_MJ_per_kg_ethane",
]

KEY_SCORE_OUTPUTS = {
    "x_c2h6",
    "s_c2h4_mol",
    "y_c2h4_kg_per_kg_ethane",
    "y_ch4_kg_per_kg_ethane",
    "y_h2_kg_per_kg_ethane",
    "y_c2h2_kg_per_kg_ethane",
    "y_c2h6_kg_per_kg_ethane",
    "y_c3_kg_per_kg_ethane",
    "y_c4plus_kg_per_kg_ethane",
    "heat_MJ_per_kg_ethane",
}


def load_csv(path: Path, outputs: list[str]) -> tuple[np.ndarray, np.ndarray]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise ValueError("dataset is empty")
    missing = [k for k in outputs if k not in rows[0]]
    if missing:
        raise ValueError("dataset missing outputs: " + ", ".join(missing))
    x = np.array(
        [[
            float(r["temperature_c"]),
            np.log10(float(r["residence_time_s"])),
            float(r["steam_hc_kgkg"]),
            float(r["pressure_bar"]),
            float(r["ramp_exponent"]),
        ] for r in rows], dtype=float
    )
    y = np.array([[float(r[k]) for k in outputs] for r in rows], dtype=float)
    good = np.isfinite(x).all(axis=1) & np.isfinite(y).all(axis=1)
    return x[good], y[good]


def transform_spec(name: str) -> dict:
    if name in {"x_c2h6", "s_c2h4_mol"}:
        return {"kind": "logit", "epsilon": 1e-7}
    return {"kind": "log", "epsilon": 1e-10}


def forward_col(y: np.ndarray, spec: dict) -> np.ndarray:
    eps = spec["epsilon"]
    if spec["kind"] == "logit":
        p = np.clip(y, eps, 1.0 - eps)
        return np.log(p / (1.0 - p))
    if spec["kind"] == "log":
        return np.log(np.maximum(y, 0.0) + eps)
    raise ValueError(spec)


def inverse_col(z: np.ndarray, spec: dict) -> np.ndarray:
    eps = spec["epsilon"]
    if spec["kind"] == "logit":
        # stable sigmoid
        out = np.empty_like(z)
        pos = z >= 0
        out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
        ez = np.exp(z[~pos])
        out[~pos] = ez / (1.0 + ez)
        return out
    if spec["kind"] == "log":
        return np.maximum(0.0, np.exp(z) - eps)
    raise ValueError(spec)


def inverse_derivative(z: np.ndarray, spec: dict) -> np.ndarray:
    if spec["kind"] == "logit":
        p = inverse_col(z, spec)
        return p * (1.0 - p)
    if spec["kind"] == "log":
        return np.exp(z)
    raise ValueError(spec)


def rbf_kernel(xa: np.ndarray, xb: np.ndarray, length: np.ndarray) -> np.ndarray:
    d = (xa[:, None, :] - xb[None, :, :]) / length[None, None, :]
    return np.exp(-0.5 * np.sum(d * d, axis=2))


def fit_gp(xn, yz, length, noise, with_inverse=True):
    k = rbf_kernel(xn, xn, length)
    k.flat[:: len(k) + 1] += noise
    l = np.linalg.cholesky(k)
    alpha = np.linalg.solve(l.T, np.linalg.solve(l, yz))
    if not with_inverse:
        return alpha, None
    eye = np.eye(len(k))
    linv = np.linalg.solve(l, eye)
    kinv = linv.T @ linv
    return alpha, kinv


def predict_mean(xtrain, xtest, alpha, length):
    k = rbf_kernel(xtest, xtrain, length)
    return k @ alpha


def predict_latent(xtrain, xtest, alpha, kinv, length):
    k = rbf_kernel(xtest, xtrain, length)
    mean_z = k @ alpha
    variance = 1.0 - np.einsum("ij,jk,ik->i", k, kinv, k)
    return mean_z, np.sqrt(np.maximum(variance, 0.0))


def original_predictions(mean_zstd, ymean, ystd, specs):
    latent = mean_zstd * ystd + ymean
    cols = [inverse_col(latent[:, j], specs[j]) for j in range(latent.shape[1])]
    return np.column_stack(cols), latent


def score_candidate(ytrue, ypred, outputs):
    scores = []
    by_output = {}
    for j, name in enumerate(outputs):
        yrange = float(np.ptp(ytrue[:, j]))
        rmse = float(np.sqrt(np.mean((ypred[:, j] - ytrue[:, j]) ** 2)))
        nrmse = rmse / yrange if yrange > 1e-12 else None
        by_output[name] = nrmse
        if name in KEY_SCORE_OUTPUTS and nrmse is not None:
            scores.append(nrmse)
    return (float(np.mean(scores)) if scores else float("inf")), by_output


def candidate_lengths(base: np.ndarray, rng: np.random.Generator, random_n: int):
    seen = set()
    out = []
    def add(a):
        a = np.clip(np.asarray(a, float), 0.035, 2.5)
        key = tuple(np.round(a, 8))
        if key not in seen:
            seen.add(key); out.append(a)
    for m in (0.45, 0.65, 0.85, 1.0, 1.2, 1.5, 1.9):
        add(base * m)
    # Independent anisotropic candidates. Log-uniform exploration allows sharp
    # ignition/severity directions and smoother pressure/dilution directions to
    # acquire different correlation lengths.
    for _ in range(random_n):
        add(np.exp(rng.uniform(np.log(0.055), np.log(1.35), size=5)))
    return out


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="multiscale/data/aramco_train.csv")
    ap.add_argument("--output", default="multiscale/surrogate.json")
    ap.add_argument("--report", default="multiscale/training_report.json")
    ap.add_argument("--length-scale", default="0.22,0.20,0.28,0.30,0.28")
    ap.add_argument("--random-kernels", type=int, default=64)
    ap.add_argument("--noise", type=float, default=2e-6)
    ap.add_argument("--tune-fraction", type=float, default=0.20)
    ap.add_argument(
        "--tune-max-points", type=int, default=256,
        help="cap the kernel-search fitting subset; the final GP still fits every point",
    )
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--outputs", default=",".join(DEFAULT_OUTPUTS))
    ap.add_argument("--round-digits", type=int, default=10)
    args = ap.parse_args()

    input_path = Path(args.input)
    outputs = [x.strip() for x in args.outputs.split(",") if x.strip()]
    base_length = np.array([float(x) for x in args.length_scale.split(",")])
    if base_length.shape != (5,):
        raise ValueError("--length-scale needs five values")
    x, y = load_csv(input_path, outputs)
    if len(x) < 32:
        raise ValueError("need at least 32 valid Cantera cases")

    specs = [transform_spec(k) for k in outputs]
    yt = np.column_stack([forward_col(y[:, j], specs[j]) for j in range(len(outputs))])

    xmin, xmax = x.min(0), x.max(0)
    span = np.maximum(xmax - xmin, 1e-12)
    xn = (x - xmin) / span
    ymean = yt.mean(0)
    ystd = yt.std(0)
    ystd[ystd < 1e-12] = 1.0
    yz = (yt - ymean) / ystd

    rng = np.random.default_rng(args.seed)
    order = rng.permutation(len(x))
    ntune = max(8, int(round(len(x) * args.tune_fraction)))
    tune_idx, fit_idx = order[:ntune], order[ntune:]
    if len(fit_idx) < 16:
        raise ValueError("tuning split leaves too few fitting points")
    search_fit_idx = fit_idx
    if args.tune_max_points > 0 and len(search_fit_idx) > args.tune_max_points:
        # Hyperparameter search on a deterministic subset keeps 640-point
        # publication builds tractable. The selected kernel is then refit once
        # on the complete training set.
        search_fit_idx = rng.choice(
            search_fit_idx, size=args.tune_max_points, replace=False
        )

    candidates = []
    best = None
    for length in candidate_lengths(base_length, rng, args.random_kernels):
        try:
            alpha0, _ = fit_gp(
                xn[search_fit_idx], yz[search_fit_idx], length, args.noise,
                with_inverse=False,
            )
        except np.linalg.LinAlgError:
            continue
        pz = predict_mean(xn[search_fit_idx], xn[tune_idx], alpha0, length)
        pred, latent = original_predictions(pz, ymean, ystd, specs)
        score, per = score_candidate(y[tune_idx], pred, outputs)
        candidates.append({
            "length_scale": length.tolist(),
            "mean_rmse_over_range": score,
            "rmse_over_range": per,
        })
        if best is None or score < best["score"]:
            best = dict(score=score, length=length)

    if best is None:
        raise RuntimeError("no stable GP kernel candidate")

    # Only the selected candidate pays the inverse-matrix cost for uncertainty
    # calibration. Final fitting below still uses every training point.
    alpha0, kinv0 = fit_gp(
        xn[search_fit_idx], yz[search_fit_idx], best["length"], args.noise
    )
    pz, sig_std = predict_latent(
        xn[search_fit_idx], xn[tune_idx], alpha0, kinv0, best["length"]
    )
    pred, latent = original_predictions(pz, ymean, ystd, specs)
    best["pred"], best["latent"], best["sig_std"] = pred, latent

    # Calibrate standard deviation after transforming it to original output units
    # with the local derivative of the inverse transform.
    base_sigma = np.empty_like(best["pred"])
    for j, spec in enumerate(specs):
        deriv = inverse_derivative(best["latent"][:, j], spec)
        base_sigma[:, j] = best["sig_std"] * ystd[j] * deriv
    residual = best["pred"] - y[tune_idx]
    ratio = residual / np.maximum(base_sigma, 1e-14)
    sigma_scale = np.sqrt(np.mean(ratio * ratio, axis=0))
    sigma_scale = np.clip(sigma_scale, 0.25, 20.0)

    alpha, kinv = fit_gp(xn, yz, best["length"], args.noise)

    def arr(a):
        return np.round(np.asarray(a), args.round_digits).tolist()

    meta_path = input_path.with_suffix(".meta.json")
    source = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    domain_min, domain_max = domain_from_source(source, xmin, xmax)

    artifact = {
        "schema": "ethane-cantera-shared-rbf-gp-v3",
        "inputs": INPUTS,
        "outputs": outputs,
        "output_transforms": specs,
        "x_min": arr(xmin), "x_max": arr(xmax),
        "domain_min": arr(domain_min), "domain_max": arr(domain_max),
        "length_scale": arr(best["length"]),
        "noise": args.noise,
        "sigma_scale": arr(sigma_scale),
        "x_train": arr(xn),
        "alpha": arr(alpha),
        "k_inv": arr(kinv),
        "y_mean": arr(ymean),
        "y_std": arr(ystd),
        "training_points": int(len(x)),
        "source": source,
        "notes": [
            "X and selectivity use logit transforms.",
            "Non-negative yields and enthalpy use log(y+epsilon) transforms.",
            "Anisotropic RBF length scales are selected on an internal tuning split.",
            "Independent release validation uses a separately generated Cantera sweep.",
            "CO and CO2 remain raw-sweep diagnostics and are not surrogate outputs in v3.",
        ],
    }
    Path(args.output).write_text(json.dumps(artifact, separators=(",", ":")), encoding="utf-8")

    tune_metrics = {}
    for j, name in enumerate(outputs):
        truth = y[tune_idx, j]; pred = best["pred"][:, j]
        e = pred - truth
        rmse = float(np.sqrt(np.mean(e * e)))
        mae = float(np.mean(np.abs(e)))
        yrange = float(np.ptp(truth))
        denom = float(np.sum((truth - truth.mean()) ** 2))
        r2 = float(1 - np.sum(e * e) / denom) if denom > 0 else None
        calibrated = base_sigma[:, j] * sigma_scale[j]
        tune_metrics[name] = {
            "mae": mae,
            "rmse": rmse,
            "rmse_over_range": rmse / yrange if yrange > 1e-12 else None,
            "r2": r2,
            "coverage_95": float(np.mean(np.abs(e) <= 1.96 * np.maximum(calibrated, 1e-15))),
            "sigma_scale": float(sigma_scale[j]),
        }

    report = {
        "schema": "ethane-cantera-gp-training-v3",
        "training_points": int(len(x)),
        "fit_points_internal": int(len(fit_idx)),
        "kernel_search_fit_points": int(len(search_fit_idx)),
        "tuning_points_internal": int(len(tune_idx)),
        "seed": args.seed,
        "kernel_candidates_evaluated": len(candidates),
        "selected_length_scale": best["length"].tolist(),
        "selected_score": best["score"],
        "internal_tuning_metrics": tune_metrics,
        "source": source,
    }
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(
        f"trained final GP on {len(x)} cases; tuned on {len(tune_idx)} internal cases; "
        f"kernel search used {len(search_fit_idx)} fit points"
    )
    print(f"evaluated {len(candidates)} kernels; selected {best['length']} score {best['score']:.5g}")
    for name, q in tune_metrics.items():
        print(f"  {name:30s} R2={q['r2']} RMSE/range={q['rmse_over_range']} 95%cov={q['coverage_95']:.3f}")
    print(f"wrote {args.output} and {args.report}")


if __name__ == "__main__":
    main()
