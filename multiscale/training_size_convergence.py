#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, json, subprocess, sys, tempfile
from pathlib import Path

SIZES=(64,128,256,512,640)
KEYS=("x_c2h6","s_c2h4_mol","y_c2h4_kg_per_kg_ethane","y_c2h2_kg_per_kg_ethane","y_c4plus_kg_per_kg_ethane","heat_MJ_per_kg_ethane")

def read_csv(path):
    with open(path,encoding="utf-8",newline="") as f:
        r=csv.DictReader(f); return r.fieldnames,list(r)

def write_subset(path,fields,rows,n):
    with open(path,"w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows[:n])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--train",default="multiscale/data/aramco_train.csv")
    ap.add_argument("--holdout",default="multiscale/data/aramco_holdout.csv")
    ap.add_argument("--output",default="multiscale/training_size_convergence.json")
    args=ap.parse_args()
    fields,rows=read_csv(args.train)
    if len(rows)<max(SIZES): raise SystemExit(f"need at least {max(SIZES)} training rows, got {len(rows)}")
    results=[]
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for n in SIZES:
            sub=td/f"train_{n}.csv"; model=td/f"gp_{n}.json"; report=td/f"train_{n}.json"; val=td/f"val_{n}.json"
            write_subset(sub,fields,rows,n)
            subprocess.run([sys.executable,"multiscale/train_gp.py","--input",str(sub),"--output",str(model),"--report",str(report),"--random-kernels","24"],check=True)
            subprocess.run([sys.executable,"multiscale/validate_surrogate.py","--model",str(model),"--data",args.holdout,"--output",str(val),"--max-nrmse","1","--min-r2","-10","--min-coverage","0"],check=True)
            v=json.loads(val.read_text())
            results.append({"training_points":n,"outputs":{k:v["outputs"][k] for k in KEYS}})
            print("N",n,{k:round(v["outputs"][k]["rmse_over_range"],5) for k in KEYS})
    out={"schema":"ethane-gp-training-size-convergence-v1","sizes":list(SIZES),"holdout":args.holdout,"results":results}
    Path(args.output).write_text(json.dumps(out,indent=2),encoding="utf-8")
if __name__=="__main__": main()
