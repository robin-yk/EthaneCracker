#!/usr/bin/env python3
"""Validate an exported Cantera-GP surrogate against a CSV dataset.

This script is intentionally separate from training so a manuscript/release build
can fail on quantitative acceptance criteria. It reports MAE, RMSE, R², maximum
absolute error, relative-to-range RMSE, and calibrated 95% interval coverage.
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


def raw_x(r):
    return np.array([
        float(r["temperature_c"]),
        math.log10(float(r["residence_time_s"])),
        float(r["steam_hc_kgkg"]),
        float(r["pressure_bar"]),
        float(r["ramp_exponent"]),
    ])


def predict(model, raw):
    xmin=np.array(model["x_min"], float)
    xmax=np.array(model["x_max"], float)
    x=(raw-xmin)/(xmax-xmin)
    xt=np.array(model["x_train"], float)
    ell=np.array(model["length_scale"], float)
    k=np.exp(-0.5*np.sum(((xt-x)/ell)**2, axis=1))
    alpha=np.array(model["alpha"], float)
    mean=np.array(model["y_mean"], float)+np.array(model["y_std"], float)*(k@alpha)
    kinv=np.array(model["k_inv"], float)
    v=max(0.0, 1.0-float(k@kinv@k))
    base=np.sqrt(v)*np.array(model["y_std"], float)
    scale=np.array(model.get("sigma_scale", np.ones(len(mean))), float)
    return mean, base*scale


def metrics(y, yp, sig):
    e=yp-y
    mae=float(np.mean(np.abs(e)))
    rmse=float(np.sqrt(np.mean(e*e)))
    maxae=float(np.max(np.abs(e)))
    denom=float(np.sum((y-y.mean())**2))
    r2=float(1-np.sum(e*e)/denom) if denom>0 else None
    yrange=float(y.max()-y.min())
    nrmse=rmse/yrange if yrange>0 else None
    coverage=float(np.mean(np.abs(e)<=1.96*np.maximum(sig,1e-15)))
    return dict(mae=mae,rmse=rmse,max_abs_error=maxae,r2=r2,
                rmse_over_range=nrmse,coverage_95=coverage)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--model", default="multiscale/surrogate.json")
    ap.add_argument("--data", default="multiscale/data/cantera_holdout.csv")
    ap.add_argument("--output", default="multiscale/validation.json")
    ap.add_argument("--max-nrmse", type=float, default=0.08)
    ap.add_argument("--min-r2", type=float, default=0.90)
    args=ap.parse_args()

    model=json.loads(Path(args.model).read_text())
    rows=load_rows(Path(args.data))
    if not rows:
        raise SystemExit("validation dataset is empty")
    outputs=model["outputs"]
    truth=np.array([[float(r[k]) for k in outputs] for r in rows],float)
    pred=[]; sigma=[]
    for r in rows:
        m,s=predict(model,raw_x(r)); pred.append(m); sigma.append(s)
    pred=np.array(pred); sigma=np.array(sigma)

    result={}
    failures=[]
    for j,name in enumerate(outputs):
        q=metrics(truth[:,j],pred[:,j],sigma[:,j])
        result[name]=q
        # Constant outputs are informative about mechanism coverage, not GP skill.
        if np.ptp(truth[:,j]) > 1e-12:
            if q["rmse_over_range"] is not None and q["rmse_over_range"] > args.max_nrmse:
                failures.append(f"{name}: RMSE/range {q['rmse_over_range']:.4g}")
            if q["r2"] is not None and q["r2"] < args.min_r2:
                failures.append(f"{name}: R2 {q['r2']:.4g}")

    report={
        "schema":"ethane-cantera-gp-validation-v1",
        "model_schema":model["schema"],
        "mechanism":model.get("source",{}).get("mechanism"),
        "validation_points":len(rows),
        "acceptance":{"max_rmse_over_range":args.max_nrmse,"min_r2":args.min_r2},
        "outputs":result,
        "passed":not failures,
        "failures":failures,
    }
    Path(args.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
    for name,q in result.items():
        print(f"{name:30s} R2={q['r2']} RMSE/range={q['rmse_over_range']} "
              f"95%cov={q['coverage_95']:.3f}")
    if failures:
        raise SystemExit("surrogate validation failed: "+"; ".join(failures))
    print(f"PASS {len(rows)} independent validation points")


if __name__=="__main__":
    main()
