#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,json
from pathlib import Path

def read(path):
    with open(path,encoding="utf-8",newline="") as f:
        r=csv.DictReader(f); return r.fieldnames,list(r)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--broad",required=True)
    ap.add_argument("--targeted")
    ap.add_argument("--output",required=True)
    args=ap.parse_args()
    fields,rows=read(args.broad)
    sources=[args.broad]
    if args.targeted:
        f2,r2=read(args.targeted)
        if f2!=fields: raise SystemExit("targeted CSV schema differs from broad CSV")
        rows.extend(r2); sources.append(args.targeted)
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    bmeta=json.loads(Path(args.broad).with_suffix(".meta.json").read_text())
    meta=dict(bmeta)
    meta["points_requested"]=len(rows);meta["points_succeeded"]=len(rows);meta["points_failed"]=0
    meta["input_ranges"]={
      "temperature_c":[750.0,1000.0],
      "residence_time_s":[0.02,1.50],
      "steam_hc_kgkg":[0.0,0.70],
      "pressure_bar":[1.0,5.0],
      "ramp_exponent":[0.45,4.0]
    }
    meta["sampling_region"]="broad+severity-targeted" if args.targeted else "broad"
    meta["component_sweeps"]=sources
    if args.targeted:
        tmeta=json.loads(Path(args.targeted).with_suffix(".meta.json").read_text())
        meta["design"]={"broad_points":bmeta["points_succeeded"],"severity_targeted_points":tmeta["points_succeeded"]}
    else:
        meta["design"]={"broad_points":bmeta["points_succeeded"],"severity_targeted_points":0}
    out.with_suffix(".meta.json").write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print("combined",len(rows),"rows from",sources)
if __name__=="__main__":main()
