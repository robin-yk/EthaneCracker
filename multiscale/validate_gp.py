#!/usr/bin/env python3
"""K-fold out-of-sample validation for the browser Gaussian-process surrogate."""

from __future__ import annotations
import argparse, csv, json
from pathlib import Path
import numpy as np

INPUTS=["temperature_c","log10_residence_time_s","steam_hc_kgkg","pressure_bar","ramp_exponent"]
OUTPUTS=[
    "x_c2h6","s_c2h4_mol","y_c2h4_kg_per_kg_ethane",
    "y_ch4_kg_per_kg_ethane","y_h2_kg_per_kg_ethane",
    "y_c2h2_kg_per_kg_ethane","heat_MJ_per_kg_ethane"
]

def load(path):
    rows=list(csv.DictReader(Path(path).open(encoding="utf-8")))
    x=np.array([[float(r["temperature_c"]),np.log10(float(r["residence_time_s"])),
                 float(r["steam_hc_kgkg"]),float(r["pressure_bar"]),float(r["ramp_exponent"])] for r in rows])
    y=np.array([[float(r[k]) for k in OUTPUTS] for r in rows])
    good=np.isfinite(x).all(1)&np.isfinite(y).all(1)
    return x[good],y[good]

def kernel(a,b,l):
    d=(a[:,None,:]-b[None,:,:])/l
    return np.exp(-0.5*np.sum(d*d,axis=2))

def fit_predict(xtr,ytr,xte,length,noise):
    xmin,xmax=xtr.min(0),xtr.max(0); span=np.maximum(xmax-xmin,1e-12)
    a=(xtr-xmin)/span; b=(xte-xmin)/span
    ym=ytr.mean(0); ys=ytr.std(0); ys[ys<1e-12]=1
    yz=(ytr-ym)/ys
    k=kernel(a,a,length); k.flat[::len(k)+1]+=noise
    L=np.linalg.cholesky(k)
    alpha=np.linalg.solve(L.T,np.linalg.solve(L,yz))
    ks=kernel(b,a,length)
    pred=(ks@alpha)*ys+ym
    # posterior variance diagonal, shared in standardized space
    v=np.linalg.solve(L,ks.T)
    var=np.maximum(0,1-np.sum(v*v,axis=0))
    sig=np.sqrt(var)[:,None]*ys[None,:]
    return pred,sig

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",default="multiscale/data/cantera_sweep.csv")
    ap.add_argument("--output",default="multiscale/validation.json")
    ap.add_argument("--folds",type=int,default=5)
    ap.add_argument("--seed",type=int,default=2026)
    ap.add_argument("--length-scale",default="0.22,0.20,0.28,0.30,0.28")
    ap.add_argument("--noise",type=float,default=2e-6)
    args=ap.parse_args()
    x,y=load(args.input); n=len(x)
    if n<max(25,args.folds*4): raise ValueError("dataset too small for requested validation")
    length=np.array([float(z) for z in args.length_scale.split(",")])
    rng=np.random.default_rng(args.seed); idx=rng.permutation(n)
    folds=np.array_split(idx,args.folds)
    truth=[]; pred=[]; sigma=[]; rowidx=[]
    for test in folds:
        train=np.setdiff1d(np.arange(n),test)
        p,s=fit_predict(x[train],y[train],x[test],length,args.noise)
        truth.append(y[test]); pred.append(p); sigma.append(s); rowidx.extend(test.tolist())
    yt=np.vstack(truth); yp=np.vstack(pred); ss=np.vstack(sigma)
    metrics={}
    for j,name in enumerate(OUTPUTS):
        e=yp[:,j]-yt[:,j]
        mae=float(np.mean(np.abs(e))); rmse=float(np.sqrt(np.mean(e*e)))
        den=float(np.sum((yt[:,j]-yt[:,j].mean())**2))
        r2=float(1-np.sum(e*e)/den) if den>0 else None
        cover=float(np.mean(np.abs(e)<=1.96*np.maximum(ss[:,j],1e-15)))
        metrics[name]={"mae":mae,"rmse":rmse,"r2":r2,"max_abs":float(np.max(np.abs(e))),
                       "coverage_95":cover,"mean_sigma":float(np.mean(ss[:,j]))}
    # retain parity points for browser plots, capped only by the input size
    parity=[]
    for i in range(len(yt)):
        parity.append({"row":int(rowidx[i]),
                       "truth":{OUTPUTS[j]:float(yt[i,j]) for j in range(len(OUTPUTS))},
                       "pred":{OUTPUTS[j]:float(yp[i,j]) for j in range(len(OUTPUTS))},
                       "sigma":{OUTPUTS[j]:float(ss[i,j]) for j in range(len(OUTPUTS))}})
    meta_path=Path(args.input).with_suffix(".meta.json")
    meta=json.loads(meta_path.read_text()) if meta_path.exists() else {}
    out={"schema":"ethane-gp-kfold-validation-v1","folds":args.folds,"seed":args.seed,
         "points":n,"length_scale":length.tolist(),"noise":args.noise,
         "metrics":metrics,"parity":parity,"source":meta}
    Path(args.output).write_text(json.dumps(out,separators=(",",":")),encoding="utf-8")
    print(json.dumps(metrics,indent=2))

if __name__=="__main__":
    main()
