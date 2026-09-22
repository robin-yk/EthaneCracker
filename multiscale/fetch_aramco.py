#!/usr/bin/env python3
"""Download official AramcoMech 3.0 files from University of Galway and convert to Cantera YAML."""

from __future__ import annotations
import argparse
import hashlib
import json
import subprocess
import urllib.request
from pathlib import Path

BASE="https://www.universityofgalway.ie/media/researchcentres/combustionchemistrycentre/files/mechanismdownloads/aramcomech30/"
FILES={
    "mechanism": "AramcoMech3.0.MECH",
    "thermo": "ARAMCOMECH30.THERM",
    "transport": "AramcoMech3.0.TRAN",
}

def fetch(url: str, path: Path) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        data=r.read()
    path.write_bytes(data)
    return {"url":url,"file":path.name,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--dir",default="multiscale/mechanisms/aramco3")
    ap.add_argument("--output",default="aramcomech3.yaml")
    ap.add_argument("--permissive",action="store_true")
    args=ap.parse_args()
    d=Path(args.dir); d.mkdir(parents=True,exist_ok=True)
    prov={}
    for k,name in FILES.items():
        prov[k]=fetch(BASE+name,d/name)
    out=d/args.output
    cmd=[
        "ck2yaml",
        f"--input={d/FILES['mechanism']}",
        f"--thermo={d/FILES['thermo']}",
        f"--transport={d/FILES['transport']}",
        f"--output={out}",
        "--name=gas",
    ]
    if args.permissive: cmd.append("--permissive")
    subprocess.run(cmd,check=True)
    prov["converted_yaml"]={
        "file":out.name,
        "bytes":out.stat().st_size,
        "sha256":hashlib.sha256(out.read_bytes()).hexdigest(),
        "converter":"Cantera ck2yaml",
    }
    (d/"provenance.json").write_text(json.dumps(prov,indent=2),encoding="utf-8")
    print(json.dumps(prov,indent=2))

if __name__=="__main__":
    main()
