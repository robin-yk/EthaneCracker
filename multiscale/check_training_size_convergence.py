#!/usr/bin/env python3
"""Training-size convergence for the ethane Cantera-GP surrogate.

The final publication model selects its kernel hyperparameters once. This script
holds those hyperparameters and all transforms fixed, then refits nested
space-filling subsets of the training design. Every subset is evaluated on the
same untouched Cantera holdout set, isolating the effect of training density.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np


def load_rows(path: Path):
    return list(csv.DictReader(path.open(encoding="utf-8")))


def raw_x(row):
    return np.array([
        float(row["temperature_c"]),
        math.log10(float(row["residence_time_s"])),
        float(row["steam_hc_kgkg"]),
        float(row["pressure_bar"]),
        float(row["ramp_exponent"]),
    ], float)


def forward(y, spec):
    eps = float(spec["epsilon"])
    if spec["kind"] == "logit":
        p = np.clip(y, eps, 1.0 - eps)
        return np.log(p / (1.0 - p))
    if spec["kind"] == "log":
        return np.log(np.maximum(y, 0.0) + eps)
    raise ValueError(spec)


def inverse(z, spec):
    eps = float(spec["epsilon"])
    if spec["kind"] == "logit":
        out = np.empty_like(z)
        pos = z >= 0
        out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
        ez = np.exp(z[~pos])
        out[~pos] = ez / (1.0 + ez)
        return out
    if spec["kind"] == "log":
        return np.maximum(0.0, np.exp(z) - eps)
    raise ValueError(spec)


def kernel(xa, xb, length):
    d = (xa[:, None, :] - xb[None, :, :]) / length[None, None, :]
    return np.exp(-0.5 * np.sum(d * d, axis=2))


def fit_alpha(x, yz, length, noise):
    k = kernel(x, x, length)
    k.flat[:: len(k) + 1] += noise
    l = np.linalg.cholesky(k)
    return np.linalg.solve(l.T, np.linalg.solve(l, yz))


def farthest_point_order(x):
    """Deterministic nested space-filling order in normalized input space."""
    n = len(x)
    if not n:
        return np.array([], dtype=int)
    center = np.full(x.shape[1], 0.5)
    first = int(np.argmin(np.sum((x - center) ** 2, axis=1)))
    chosen = np.empty(n, dtype=int)
    chosen[0] = first
    min_d2 = np.sum((x - x[first]) ** 2, axis=1)
    min_d2[first] = -1.0
    for i in range(1, n):
        nxt = int(np.argmax(min_d2))
        chosen[i] = nxt
        d2 = np.sum((x - x[nxt]) ** 2, axis=1)
        min_d2 = np.minimum(min_d2, d2)
        min_d2[chosen[: i + 1]] = -1.0
    return chosen


def metric(y, yp):
    e = yp - y
    rmse = float(np.sqrt(np.mean(e * e)))
    mae = float(np.mean(np.abs(e)))
    maxae = float(np.max(np.abs(e)))
    yrange = float(np.ptp(y))
    denom = float(np.sum((y - y.mean()) ** 2))
    return {
        "mae": mae,
        "rmse": rmse,
        "max_abs_error": maxae,
        "rmse_over_range": rmse / yrange if yrange > 1e-12 else None,
        "r2": float(1.0 - np.sum(e * e) / denom) if denom > 1e-30 else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="multiscale/surrogate.json")
    ap.add_argument("--train", default="multiscale/data/aramco_train.csv")
    ap.add_argument("--holdout", default="multiscale/data/aramco_holdout.csv")
    ap.add_argument("--sizes", default="64,128,256,512,640")
    ap.add_argument("--output", default="multiscale/training_size_convergence.json")
    args = ap.parse_args()

    model = json.loads(Path(args.model).read_text())
    train = load_rows(Path(args.train))
    holdout = load_rows(Path(args.holdout))
    outputs = model["outputs"]
    specs = model["output_transforms"]

    x_min = np.array(model["x_min"], float)
    x_max = np.array(model["x_max"], float)
    span = np.maximum(x_max - x_min, 1e-12)
    x_train = np.array([raw_x(r) for r in train])
    x_hold = np.array([raw_x(r) for r in holdout])
    xn = (x_train - x_min) / span
    xh = (x_hold - x_min) / span

    y_train = np.array([[float(r[k]) for k in outputs] for r in train], float)
    y_hold = np.array([[float(r[k]) for k in outputs] for r in holdout], float)
    yt = np.column_stack([
        forward(y_train[:, j], specs[j]) for j in range(len(outputs))
    ])
    y_mean = np.array(model["y_mean"], float)
    y_std = np.array(model["y_std"], float)
    yz = (yt - y_mean) / y_std

    length = np.array(model["length_scale"], float)
    noise = float(model["noise"])
    order = farthest_point_order(xn)
    requested = [int(x) for x in args.sizes.split(",") if x.strip()]
    sizes = [n for n in requested if 16 <= n <= len(train)]
    if not sizes:
        raise SystemExit("no requested convergence size fits the training dataset")

    result = {}
    for n in sizes:
        idx = order[:n]
        alpha = fit_alpha(xn[idx], yz[idx], length, noise)
        zstd = kernel(xh, xn[idx], length) @ alpha
        latent = zstd * y_std + y_mean
        pred = np.column_stack([
            inverse(latent[:, j], specs[j]) for j in range(len(outputs))
        ])
        by_output = {}
        scores = []
        for j, name in enumerate(outputs):
            q = metric(y_hold[:, j], pred[:, j])
            by_output[name] = q
            if q["rmse_over_range"] is not None:
                scores.append(q["rmse_over_range"])
        result[str(n)] = {
            "training_points": n,
            "mean_rmse_over_range": float(np.mean(scores)),
            "max_rmse_over_range": float(np.max(scores)),
            "outputs": by_output,
        }
        print(
            f"N={n:4d} mean RMSE/range={result[str(n)]['mean_rmse_over_range']:.5f} "
            f"max={result[str(n)]['max_rmse_over_range']:.5f}"
        )

    largest = str(max(sizes))
    report = {
        "schema": "ethane-cantera-gp-training-size-convergence-v1",
        "method": (
            "nested farthest-point subsets in normalized 5D input space; "
            "final-model transforms, length scales and noise held fixed; "
            "common untouched Cantera holdout"
        ),
        "training_points_available": len(train),
        "holdout_points": len(holdout),
        "requested_sizes": requested,
        "evaluated_sizes": sizes,
        "selected_length_scale": model["length_scale"],
        "noise": model["noise"],
        "results": result,
        "full_training_score": result[largest]["mean_rmse_over_range"],
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
