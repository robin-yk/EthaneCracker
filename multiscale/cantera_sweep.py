#!/usr/bin/env python3
"""
Generate a mechanism-resolved ethane-cracking design space with Cantera.

A Lagrangian plug-flow approximation advances a fluid element through a prescribed
temperature history using constant-pressure, isothermal reactor segments. Chemistry
is solved by Cantera in each segment. The thermal history is

    T(f) = Tin + (Tout - Tin) * f**ramp_exponent

where f is normalized residence time from 0 to 1.

All product yields are reported per kg of ethane entering the reactor. The plant
recycle calculation can therefore recover:
    coil ethane / kg ethylene = 1 / y_C2H4
    recycle ethane / kg ethylene = (1-X) / y_C2H4
    fresh ethane / kg ethylene = X / y_C2H4
under the stated ideal ethane-recovery assumption.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import platform
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cantera as ct
import numpy as np


INPUT_RANGES = {
    "temperature_c": (750.0, 1000.0),
    "residence_time_s": (0.02, 1.00),  # sampled log-uniform
    "steam_hc_kgkg": (0.0, 0.70),
    "pressure_bar": (1.0, 5.0),
    "ramp_exponent": (0.45, 4.0),
}

OUTPUT_SPECIES = ("C2H4", "CH4", "H2", "C2H2", "C2H6", "CO", "CO2")


def file_sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def latin_hypercube(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    x = np.empty((n, d), dtype=float)
    for j in range(d):
        perm = rng.permutation(n)
        x[:, j] = (perm + rng.random(n)) / n
    return x


def scale_samples(unit: np.ndarray) -> list[dict[str, float]]:
    rows: list[dict[str, float]] = []
    for u in unit:
        t = INPUT_RANGES["temperature_c"][0] + u[0] * (
            INPUT_RANGES["temperature_c"][1] - INPUT_RANGES["temperature_c"][0]
        )
        log_tau = math.log10(INPUT_RANGES["residence_time_s"][0]) + u[1] * (
            math.log10(INPUT_RANGES["residence_time_s"][1])
            - math.log10(INPUT_RANGES["residence_time_s"][0])
        )
        steam = INPUT_RANGES["steam_hc_kgkg"][0] + u[2] * (
            INPUT_RANGES["steam_hc_kgkg"][1] - INPUT_RANGES["steam_hc_kgkg"][0]
        )
        p = INPUT_RANGES["pressure_bar"][0] + u[3] * (
            INPUT_RANGES["pressure_bar"][1] - INPUT_RANGES["pressure_bar"][0]
        )
        ramp = INPUT_RANGES["ramp_exponent"][0] + u[4] * (
            INPUT_RANGES["ramp_exponent"][1] - INPUT_RANGES["ramp_exponent"][0]
        )
        rows.append(
            dict(
                temperature_c=float(t),
                residence_time_s=float(10**log_tau),
                steam_hc_kgkg=float(steam),
                pressure_bar=float(p),
                ramp_exponent=float(ramp),
            )
        )
    return rows


def species_mass(gas: ct.Solution, total_mass_kg: float, species: str) -> float:
    if species not in gas.species_names:
        return 0.0
    return total_mass_kg * float(gas[species].Y[0])


def species_kmol(gas: ct.Solution, total_mass_kg: float, species: str) -> float:
    if species not in gas.species_names:
        return 0.0
    k = gas.species_index(species)
    return total_mass_kg * float(gas.Y[k]) / float(gas.molecular_weights[k])


def carbon_lumps(gas: ct.Solution, total_mass_kg: float) -> tuple[float, float]:
    """Return total C3 and C4+ species mass, kg, from the outlet state."""
    c3 = 0.0
    c4plus = 0.0
    for k, name in enumerate(gas.species_names):
        nc = gas.n_atoms(name, "C")
        if nc == 3:
            c3 += total_mass_kg * float(gas.Y[k])
        elif nc >= 4:
            c4plus += total_mass_kg * float(gas.Y[k])
    return c3, c4plus


def simulate_case(
    gas: ct.Solution,
    temperature_c: float,
    residence_time_s: float,
    steam_hc_kgkg: float,
    pressure_bar: float,
    ramp_exponent: float,
    inlet_temperature_c: float,
    segments: int,
) -> dict[str, float]:
    required = {"C2H6", "H2O", "C2H4"}
    missing = sorted(required.difference(gas.species_names))
    if missing:
        raise ValueError(f"mechanism is missing required species: {', '.join(missing)}")

    mw_ethane = float(gas.molecular_weights[gas.species_index("C2H6")])
    mw_water = float(gas.molecular_weights[gas.species_index("H2O")])

    # Basis: 1 kmol C2H6 entering the reactor.
    fresh_ethane_kmol = 1.0
    fresh_ethane_mass = mw_ethane
    steam_mass = steam_hc_kgkg * fresh_ethane_mass
    steam_kmol = steam_mass / mw_water
    total_mass = fresh_ethane_mass + steam_mass

    p_pa = pressure_bar * 1e5
    tin_k = inlet_temperature_c + 273.15
    tout_k = temperature_c + 273.15

    gas.TPX = tin_k, p_pa, {"C2H6": fresh_ethane_kmol, "H2O": steam_kmol}
    h_in = float(gas.enthalpy_mass)
    y = gas.Y.copy()

    # Reuse one ReactorNet per operating point. The imposed temperature is updated
    # between integration intervals, then the reactor/integrator state is synchronized.
    # This is materially faster for large detailed mechanisms than constructing a new
    # CVODE system for every temperature segment.
    dt = residence_time_s / segments
    gas.TPY = tin_k, p_pa, y
    reactor = ct.IdealGasConstPressureReactor(
        gas, energy="off", clone=False, name="pfr-fluid-element"
    )
    net = ct.ReactorNet([reactor])
    net.rtol = 1e-8
    net.atol = 1e-15
    for i in range(segments):
        f = (i + 0.5) / segments
        t_k = tin_k + (tout_k - tin_k) * (f**ramp_exponent)
        y = reactor.phase.Y.copy()
        gas.TPY = t_k, p_pa, y
        reactor.syncState()
        net.reinitialize()
        net.advance((i + 1) * dt)
    y = reactor.phase.Y.copy()

    gas.TPY = tout_k, p_pa, y
    h_out = float(gas.enthalpy_mass)

    ethane_out = species_kmol(gas, total_mass, "C2H6")
    ethylene_out = species_kmol(gas, total_mass, "C2H4")
    consumed = max(0.0, fresh_ethane_kmol - ethane_out)
    conversion = consumed / fresh_ethane_kmol
    selectivity = ethylene_out / consumed if consumed > 1e-12 else 0.0

    result: dict[str, float] = {
        "temperature_c": temperature_c,
        "residence_time_s": residence_time_s,
        "steam_hc_kgkg": steam_hc_kgkg,
        "pressure_bar": pressure_bar,
        "ramp_exponent": ramp_exponent,
        "x_c2h6": conversion,
        "s_c2h4_mol": selectivity,
        "heat_MJ_per_kg_ethane": (h_out - h_in) * total_mass / fresh_ethane_mass / 1e6,
    }

    for sp in OUTPUT_SPECIES:
        key = sp.lower()
        result[f"y_{key}_kg_per_kg_ethane"] = (
            species_mass(gas, total_mass, sp) / fresh_ethane_mass
        )

    c3, c4plus = carbon_lumps(gas, total_mass)
    result["y_c3_kg_per_kg_ethane"] = c3 / fresh_ethane_mass
    result["y_c4plus_kg_per_kg_ethane"] = c4plus / fresh_ethane_mass

    # Elemental and total-mass closure.
    c_in = fresh_ethane_kmol * 2.0
    h_in_atoms = fresh_ethane_kmol * 6.0 + steam_kmol * 2.0
    o_in = steam_kmol
    c_out = h_out_atoms = o_out = 0.0
    for k, sp_name in enumerate(gas.species_names):
        n_k = total_mass * float(gas.Y[k]) / float(gas.molecular_weights[k])
        c_out += n_k * gas.n_atoms(sp_name, "C")
        h_out_atoms += n_k * gas.n_atoms(sp_name, "H")
        o_out += n_k * gas.n_atoms(sp_name, "O")
    result["carbon_residual"] = (c_out - c_in) / max(c_in, 1e-30)
    result["hydrogen_residual"] = (h_out_atoms - h_in_atoms) / max(h_in_atoms, 1e-30)
    result["oxygen_residual"] = (o_out - o_in) / max(o_in, 1e-30) if o_in else o_out
    result["mass_residual"] = float(gas.Y.sum() - 1.0)

    return result


_WORKER_GAS = None
_WORKER_INLET_T = None
_WORKER_SEGMENTS = None


def _init_worker(mechanism: str, phase: str, inlet_temperature_c: float, segments: int):
    global _WORKER_GAS, _WORKER_INLET_T, _WORKER_SEGMENTS
    _WORKER_GAS = ct.Solution(mechanism, phase)
    _WORKER_INLET_T = inlet_temperature_c
    _WORKER_SEGMENTS = segments


def _worker(case: dict[str, float]):
    try:
        return {
            "ok": True,
            "row": simulate_case(
                _WORKER_GAS,
                inlet_temperature_c=_WORKER_INLET_T,
                segments=_WORKER_SEGMENTS,
                **case,
            ),
        }
    except Exception as exc:
        return {"ok": False, "case": case, "error": str(exc)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mechanism", default="gri30.yaml")
    ap.add_argument("--phase", default="gri30")
    ap.add_argument("--points", type=int, default=256)
    ap.add_argument("--segments", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--inlet-temperature-c", type=float, default=650.0)
    ap.add_argument("--output", default="multiscale/data/cantera_sweep.csv")
    ap.add_argument(
        "--workers", type=int, default=0,
        help="parallel worker processes; 0 selects up to four CPUs",
    )
    args = ap.parse_args()

    gas = ct.Solution(args.mechanism, args.phase)
    rng = np.random.default_rng(args.seed)
    cases = scale_samples(latin_hypercube(args.points, 5, rng))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    failures = []
    workers = args.workers if args.workers > 0 else min(4, os.cpu_count() or 1)
    print(f"running {args.points} cases with {workers} worker(s)")

    if workers == 1:
        _init_worker(args.mechanism, args.phase, args.inlet_temperature_c, args.segments)
        results = map(_worker, cases)
        pool = None
    else:
        pool = ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            initargs=(args.mechanism, args.phase, args.inlet_temperature_c, args.segments),
        )
        results = pool.map(_worker, cases, chunksize=1)

    try:
        for i, result in enumerate(results, 1):
            if result["ok"]:
                rows.append(result["row"])
            else:
                failures.append({"case": i, **result["case"], "error": result["error"]})
            if i % max(1, args.points // 20) == 0 or i == args.points:
                print(f"{i}/{args.points} cases; {len(failures)} failed")
    finally:
        if pool is not None:
            pool.shutdown()

    if not rows:
        raise RuntimeError("all Cantera cases failed")

    fields = list(rows[0].keys())
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    mech_path = Path(args.mechanism)
    provenance_path = mech_path.with_suffix(".provenance.json")
    mechanism_provenance = (
        json.loads(provenance_path.read_text())
        if provenance_path.exists()
        else None
    )
    meta = {
        "mechanism": args.mechanism,
        "mechanism_sha256": file_sha256(mech_path),
        "mechanism_species": gas.n_species,
        "mechanism_reactions": gas.n_reactions,
        "mechanism_provenance": mechanism_provenance,
        "phase": args.phase,
        "cantera_version": ct.__version__,
        "python_version": platform.python_version(),
        "git_sha": os.getenv("GITHUB_SHA"),
        "points_requested": args.points,
        "points_succeeded": len(rows),
        "points_failed": len(failures),
        "segments": args.segments,
        "workers": workers,
        "seed": args.seed,
        "inlet_temperature_c": args.inlet_temperature_c,
        "input_ranges": INPUT_RANGES,
        "reactor_model": "prescribed-temperature Lagrangian PFR approximation",
        "thermal_history": "T(f)=Tin+(Tout-Tin)*f**ramp_exponent",
        "yield_basis": "kg species per kg ethane entering reactor",
        "failures": failures,
    }
    output.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(
        f"wrote {len(rows)} cases to {output}; mechanism "
        f"{gas.n_species} species / {gas.n_reactions} reactions"
    )


if __name__ == "__main__":
    main()
