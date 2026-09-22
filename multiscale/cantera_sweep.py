#!/usr/bin/env python3
"""
Generate a mechanism-resolved ethane-cracking design space with Cantera.

The reactor is a Lagrangian plug-flow approximation: a fluid element is advanced
through a prescribed temperature history using a sequence of constant-pressure,
isothermal reactor segments. Chemistry is solved by Cantera in every segment.

The default mechanism is gri30.yaml only so the script runs with a stock Cantera
installation. GRI-Mech is a demonstration mechanism and should be replaced with
a validated ethane-pyrolysis mechanism (for example an AramcoMech Cantera YAML)
before research conclusions are drawn.

Outputs are per kg of fresh ethane, excluding dilution steam from the denominator.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
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

OUTPUT_SPECIES = ("C2H4", "CH4", "H2", "C2H2", "C3H6", "C3H8")


def latin_hypercube(n: int, d: int, rng: np.random.Generator) -> np.ndarray:
    """Simple max-coverage Latin hypercube on [0, 1]^d."""
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
            {
                "temperature_c": float(t),
                "residence_time_s": float(10**log_tau),
                "steam_hc_kgkg": float(steam),
                "pressure_bar": float(p),
                "ramp_exponent": float(ramp),
            }
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


def simulate_case(
    mechanism: str,
    phase: str,
    temperature_c: float,
    residence_time_s: float,
    steam_hc_kgkg: float,
    pressure_bar: float,
    ramp_exponent: float,
    inlet_temperature_c: float,
    segments: int,
) -> dict[str, float]:
    gas = ct.Solution(mechanism, phase)

    required = {"C2H6", "H2O", "C2H4"}
    missing = sorted(required.difference(gas.species_names))
    if missing:
        raise ValueError(f"mechanism is missing required species: {', '.join(missing)}")

    mw_ethane = float(gas.molecular_weights[gas.species_index("C2H6")])
    mw_water = float(gas.molecular_weights[gas.species_index("H2O")])

    # Basis: 1 kmol fresh C2H6. Molecular weights in Cantera are kg/kmol.
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

    dt = residence_time_s / segments
    for i in range(segments):
        f = (i + 0.5) / segments
        t_k = tin_k + (tout_k - tin_k) * (f**ramp_exponent)
        gas.TPY = t_k, p_pa, y
        reactor = ct.IdealGasConstPressureReactor(gas, energy="off")
        net = ct.ReactorNet([reactor])
        net.rtol = 1e-8
        net.atol = 1e-15
        net.advance(dt)
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
        key = sp.lower().replace("+", "plus")
        result[f"y_{key}_kg_per_kg_ethane"] = (
            species_mass(gas, total_mass, sp) / fresh_ethane_mass
        )

    # Elemental closure is useful for rejecting mechanism/configuration mistakes.
    c_in = fresh_ethane_kmol * 2.0
    c_out = 0.0
    h_in_atoms = fresh_ethane_kmol * 6.0 + steam_kmol * 2.0
    h_out_atoms = 0.0
    o_in = steam_kmol
    o_out = 0.0
    for k, sp_name in enumerate(gas.species_names):
        n_k = total_mass * float(gas.Y[k]) / float(gas.molecular_weights[k])
        c_out += n_k * gas.n_atoms(sp_name, "C")
        h_out_atoms += n_k * gas.n_atoms(sp_name, "H")
        o_out += n_k * gas.n_atoms(sp_name, "O")
    result["carbon_residual"] = (c_out - c_in) / max(c_in, 1e-30)
    result["hydrogen_residual"] = (h_out_atoms - h_in_atoms) / max(h_in_atoms, 1e-30)
    result["oxygen_residual"] = (o_out - o_in) / max(o_in, 1e-30) if o_in else o_out

    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mechanism", default="gri30.yaml")
    ap.add_argument("--phase", default="gri30")
    ap.add_argument("--points", type=int, default=256)
    ap.add_argument("--segments", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--inlet-temperature-c", type=float, default=650.0)
    ap.add_argument("--output", default="multiscale/data/cantera_sweep.csv")
    args = ap.parse_args()

    rng = np.random.default_rng(args.seed)
    unit = latin_hypercube(args.points, 5, rng)
    cases = scale_samples(unit)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    failures = []
    for i, case in enumerate(cases, 1):
        try:
            rows.append(
                simulate_case(
                    args.mechanism,
                    args.phase,
                    inlet_temperature_c=args.inlet_temperature_c,
                    segments=args.segments,
                    **case,
                )
            )
        except Exception as exc:  # preserve failed locations for audit
            failures.append({"case": i, **case, "error": str(exc)})
        if i % max(1, args.points // 20) == 0 or i == args.points:
            print(f"{i}/{args.points} cases; {len(failures)} failed")

    if not rows:
        raise RuntimeError("all Cantera cases failed")

    fields = list(rows[0].keys())
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    meta = {
        "mechanism": args.mechanism,
        "phase": args.phase,
        "points_requested": args.points,
        "points_succeeded": len(rows),
        "points_failed": len(failures),
        "segments": args.segments,
        "seed": args.seed,
        "inlet_temperature_c": args.inlet_temperature_c,
        "input_ranges": INPUT_RANGES,
        "reactor_model": "prescribed-temperature Lagrangian PFR approximation",
        "failures": failures,
    }
    output.with_suffix(".meta.json").write_text(
        json.dumps(meta, indent=2), encoding="utf-8"
    )
    print(f"wrote {len(rows)} cases to {output}")


if __name__ == "__main__":
    main()
