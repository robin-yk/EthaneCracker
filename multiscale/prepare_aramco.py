#!/usr/bin/env python3
"""Fetch the official AramcoMech 3.0 Chemkin files and convert them to Cantera YAML.

The source URLs point to the University of Galway Combustion Chemistry Centre.
Raw mechanism files are downloaded at build time rather than vendored. A provenance
JSON records URLs, SHA-256 digests, retrieval time, Cantera version, and the final
YAML digest so every surrogate can identify the exact chemical model it used.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

import cantera as ct

BASE = (
    "https://www.universityofgalway.ie/media/researchcentres/"
    "combustionchemistrycentre/files/mechanismdownloads/aramcomech30/"
)
FILES = {
    "mechanism": ("AramcoMech3.0.MECH", BASE + "AramcoMech3.0.MECH"),
    "thermo": ("ARAMCOMECH30.THERM", BASE + "ARAMCOMECH30.THERM"),
    "transport": ("AramcoMech3.0.TRAN", BASE + "AramcoMech3.0.TRAN"),
}
REFERENCE = {
    "title": (
        "An experimental and chemical kinetic modeling study of 1,3-butadiene "
        "combustion: Ignition delay time and laminar flame speed measurements"
    ),
    "authors": "Zhou et al.",
    "journal": "Combustion and Flame 197 (2018) 423-438",
    "doi": "10.1016/j.combustflame.2018.08.006",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download(url: str, dest: Path) -> None:
    req = Request(url, headers={"User-Agent": "TEA-EthaneCracking reproducibility build"})
    with urlopen(req, timeout=60) as r, dest.open("wb") as f:
        while True:
            block = r.read(1024 * 1024)
            if not block:
                break
            f.write(block)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--directory", default="multiscale/mechanisms/aramcomech30")
    ap.add_argument("--output", default="multiscale/mechanisms/aramcomech30/aramcomech30.yaml")
    ap.add_argument("--force-download", action="store_true")
    ap.add_argument("--permissive", action="store_true", default=True)
    args = ap.parse_args()

    root = Path(args.directory)
    root.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    sources = {}

    for key, (name, url) in FILES.items():
        p = root / name
        if args.force_download or not p.exists():
            print(f"fetch {url}")
            download(url, p)
        paths[key] = p
        sources[key] = {
            "url": url,
            "filename": name,
            "bytes": p.stat().st_size,
            "sha256": sha256(p),
        }

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, "-m", "cantera.ck2yaml",
        f"--input={paths['mechanism']}",
        f"--thermo={paths['thermo']}",
        f"--transport={paths['transport']}",
        "--name=gas",
        f"--output={out}",
    ]
    if args.permissive:
        cmd.append("--permissive")
    print("convert:", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)

    gas = ct.Solution(str(out), "gas")
    provenance = {
        "mechanism_name": "AramcoMech 3.0",
        "mechanism_release": 2018,
        "official_source": (
            "University of Galway Combustion Chemistry Centre mechanism downloads"
        ),
        "reference": REFERENCE,
        "retrieved_utc": datetime.now(timezone.utc).isoformat(),
        "cantera_version": ct.__version__,
        "phase": "gas",
        "species": gas.n_species,
        "reactions": gas.n_reactions,
        "source_files": sources,
        "yaml": {
            "filename": out.name,
            "bytes": out.stat().st_size,
            "sha256": sha256(out),
        },
    }
    prov = out.with_suffix(".provenance.json")
    prov.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    print(
        f"validated {out}: {gas.n_species} species, {gas.n_reactions} reactions, "
        f"sha256 {provenance['yaml']['sha256']}"
    )
    print(f"wrote {prov}")


if __name__ == "__main__":
    main()
