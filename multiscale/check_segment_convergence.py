#!/usr/bin/env python3
"""Check discretization convergence of the prescribed-temperature PFR."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import cantera as ct

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cantera_sweep import simulate_case


CASES = [
    dict(name="baseline", temperature_c=850.0, residence_time_s=0.35,
         steam_hc_kgkg=0.35, pressure_bar=1.5, ramp_exponent=1.0),
    dict(name="rapid-high", temperature_c=950.0, residence_time_s=0.08,
         steam_hc_kgkg=0.35, pressure_bar=1.5, ramp_exponent=0.60),
    dict(name="slow-dilute", temperature_c=800.0, residence_time_s=0.60,
         steam_hc_kgkg=0.50, pressure_bar=4.0, ramp_exponent=2.0),
    dict(name="short-low-pressure", temperature_c=900.0, residence_time_s=0.05,
         steam_hc_kgkg=0.20, pressure_bar=1.0, ramp_exponent=0.50),
    dict(name="late-heating", temperature_c=925.0, residence_time_s=0.25,
         steam_hc_kgkg=0.30, pressure_bar=3.0, ramp_exponent=3.5),
]

KEYS = ["x_c2h6", "s_c2h4_mol", "y_c2h4_kg_per_kg_ethane", "heat_MJ_per_kg_ethane"]


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mechanism",required=True)
    ap.add_argument("--phase",default="gas")
    ap.add_argument("--coarse",type=int,default=20)
    ap.add_argument("--reference",type=int,default=40)
    ap.add_argument("--max-xs-abs",type=float,default=0.005)
    ap.add_argument("--max-yield-abs",type=float,default=0.005)
    ap.add_argument("--max-heat-rel",type=float,default=0.01)
    ap.add_argument("--output",default="multiscale/segment_convergence.json")
    args=ap.parse_args()

    gas=ct.Solution(args.mechanism,args.phase)
    rows=[]; failures=[]
    for case in CASES:
        params={k:v for k,v in case.items() if k!="name"}
        a=simulate_case(gas,inlet_temperature_c=650.0,segments=args.coarse,**params)
        b=simulate_case(gas,inlet_temperature_c=650.0,segments=args.reference,**params)
        d={}
        for key in KEYS:
            av,bv=a[key],b[key]
            d[key]={
                "coarse":av,"reference":bv,
                "abs_error":abs(av-bv),
                "relative_error":abs(av-bv)/max(abs(bv),1e-12),
            }
        if d["x_c2h6"]["abs_error"]>args.max_xs_abs:
            failures.append(f"{case['name']} conversion")
        if d["s_c2h4_mol"]["abs_error"]>args.max_xs_abs:
            failures.append(f"{case['name']} selectivity")
        if d["y_c2h4_kg_per_kg_ethane"]["abs_error"]>args.max_yield_abs:
            failures.append(f"{case['name']} ethylene yield")
        if d["heat_MJ_per_kg_ethane"]["relative_error"]>args.max_heat_rel:
            failures.append(f"{case['name']} enthalpy")
        rows.append({"case":case,"metrics":d})

    report={
        "schema":"ethane-pfr-segment-convergence-v1",
        "coarse_segments":args.coarse,
        "reference_segments":args.reference,
        "acceptance":{
            "max_conversion_selectivity_abs":args.max_xs_abs,
            "max_ethylene_yield_abs":args.max_yield_abs,
            "max_enthalpy_relative":args.max_heat_rel,
        },
        "cases":rows,
        "passed":not failures,
        "failures":failures,
    }
    Path(args.output).write_text(json.dumps(report,indent=2),encoding="utf-8")
    for row in rows:
        print(row["case"]["name"])
        for k,q in row["metrics"].items():
            print(" ",k,"abs",q["abs_error"],"rel",q["relative_error"])
    if failures:
        raise SystemExit("segment convergence failed: "+", ".join(failures))
    print("PASS segment convergence")


if __name__=="__main__":
    main()
