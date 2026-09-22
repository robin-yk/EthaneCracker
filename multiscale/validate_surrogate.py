#!/usr/bin/env python3
"""Independent validation of the exported Cantera-GP browser surrogate."""

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


def inverse_scalar(z: float, spec: dict) -> tuple[float, float]:
    """Return inverse-transformed mean and d(original)/d(latent)."""
    eps = spec["epsilon"]
    if spec["kind"] == "logit":
        if z >= 0:
            p = 1.0 / (1.0 + math.exp(-z))
        else:
            e = math.exp(z); p = e / (1.0 + e)
        return p, p * (1.0 - p)
    if spec["kind"] == "log":
        ez = math.exp(z)
        return max(0.0, ez - eps), ez
    raise ValueError(spec)


def predict(model, raw):
    xmin=np.array(model["x_min"], float); xmax=np.array(model["x_max"], float)
    x=(raw-xmin)/(xmax-xmin)
    xt=np.array(model["x_train"], float)
    ell=np.array(model["length_scale"], float)
    k=np.exp(-0.5*np.sum(((xt-x)/ell)**2, axis=1))
    alpha=np.array(model["alpha"], float)
    zstd=k@alpha
    latent=np.array(model["y_mean"], float)+np.array(model["y_std"], float)*zstd
    kinv=np.array(model["k_inv"], float)
    v=max(0.0, 1.0-float(k@kinv@k))
    sigma_std=math.sqrt(v)
    scale=np.array(model.get("sigma_scale",np.ones(len(latent))),float)
    means=[]; sigmas=[]
    for j,spec in enumerate(model["output_transforms"]):
        mean,deriv=inverse_scalar(float(latent[j]),spec)
        means.append(mean)
        sigmas.append(sigma_std*float(model["y_std"][j])*deriv*scale[j])
    return np.array(means),np.array(sigmas)


def metrics(y, yp, sig):
    e=yp-y
    mae=float(np.mean(np.abs(e)))
    rmse=float(np.sqrt(np.mean(e*e)))
    maxae=float(np.max(np.abs(e)))
    denom=float(np.sum((y-y.mean())**2))
    r2=float(1-np.sum(e*e)/denom) if denom>1e-30 else None
    yrange=float(y.max()-y.min())
    nrmse=rmse/yrange if yrange>1e-12 else None
    coverage=float(np.mean(np.abs(e)<=1.96*np.maximum(sig,1e-15)))
    return dict(mae=mae,rmse=rmse,max_abs_error=maxae,r2=r2,
                rmse_over_range=nrmse,coverage_95=coverage,
                min_true=float(y.min()),max_true=float(y.max()),
                min_pred=float(yp.min()),max_pred=float(yp.max()))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--model",default="multiscale/surrogate.json")
    ap.add_argument("--data",default="multiscale/data/aramco_holdout.csv")
    ap.add_argument("--output",default="multiscale/validation.json")
    ap.add_argument("--max-nrmse",type=float,default=0.08)
    ap.add_argument("--min-r2",type=float,default=0.90)
    ap.add_argument("--min-coverage",type=float,default=0.80)
    args=ap.parse_args()

    model=json.loads(Path(args.model).read_text())
    if model["schema"]!="ethane-cantera-shared-rbf-gp-v3":
        raise SystemExit("validation expects GP schema v3")
    rows=load_rows(Path(args.data))
    if not rows: raise SystemExit("validation dataset is empty")
    outputs=model["outputs"]
    truth=np.array([[float(r[k]) for k in outputs] for r in rows],float)
    pred=[];sigma=[]
    for r in rows:
        m,s=predict(model,raw_x(r));pred.append(m);sigma.append(s)
    pred=np.array(pred);sigma=np.array(sigma)

    result={};failures=[]
    for j,name in enumerate(outputs):
        q=metrics(truth[:,j],pred[:,j],sigma[:,j]);result[name]=q
        # Every deployed output is release-gated unless its observed holdout range
        # is numerically constant, in which case R2/range metrics are undefined.
        if q["rmse_over_range"] is not None:
            if q["rmse_over_range"]>args.max_nrmse:
                failures.append(f"{name}: RMSE/range {q['rmse_over_range']:.4g}")
            if q["r2"] is not None and q["r2"]<args.min_r2:
                failures.append(f"{name}: R2 {q['r2']:.4g}")
        if q["coverage_95"]<args.min_coverage:
            failures.append(f"{name}: 95% interval coverage {q['coverage_95']:.3f}")

    report={
        "schema":"ethane-cantera-gp-validation-v3",
        "model_schema":model["schema"],
        "mechanism":model.get("source",{}).get("mechanism"),
        "validation_points":len(rows),
        "acceptance":{
            "max_rmse_over_range":args.max_nrmse,
            "min_r2":args.min_r2,
            "min_95_interval_coverage":args.min_coverage,
        },
        "outputs":result,
        "passed":not failures,
        "failures":failures,
    }
    Path(args.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
    for name,q in result.items():
        print(f"{name:30s} R2={q['r2']} RMSE/range={q['rmse_over_range']} 95%cov={q['coverage_95']:.3f}")
    if failures:
        raise SystemExit("surrogate validation failed: "+"; ".join(failures))
    print(f"PASS {len(rows)} independent validation points")


if __name__=="__main__":
    main()
