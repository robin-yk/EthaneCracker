"""Cold-end temperature of the ethane-cracker cold box from vapor-liquid equilibrium.

Step 1 of the cold-box reassessment (2026-10-14). The published model sets the
cold-end temperature with a screening correlation,

    t_c = -100 - 40 log10(0.01/(1 - r_E)) - 160 (phi - 0.40)   [degC]

where phi is the methane-plus-hydrogen mole fraction of the cold-box feed and
r_E = 0.995 is the ethylene recovery. This script replaces the correlation with
a flash calculation: at the cold-box pressure, find the temperature at which a
single equilibrium stage leaves 0.5 % of the ethylene in the vapor (tail gas).

Feeds are read from the model's own output files, so the compositions are the
ones the published model used:
  - reference fired case: outputs/screening/data/scenarios.json, baseline.gp_fired
  - Wang et al. comparison: outputs/screening/data/wang-downstream.json,
    published Table 5 composition and the GP-predicted composition

Thermodynamics: Peng-Robinson equation of state with the ChemSep binary
interaction parameters shipped with the `thermo` library. A kij = 0 case is
included to show the sensitivity to those parameters.

Run with the ethane-coldbox environment from this folder:
    ~/.venvs/ethane-coldbox/bin/python coldbox_vle.py
Writes coldbox-vle-results.json next to this file.
"""
import json
import math
import os

from scipy.optimize import brentq
from thermo import CEOSGas, CEOSLiquid, ChemicalConstantsPackage, FlashVL, PRMIX
from thermo.interaction_parameters import IPDB

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "outputs", "screening", "data")

NAMES = ["hydrogen", "methane", "ethylene", "ethane", "propylene", "1-butene"]
MW = {"hydrogen": 2.016, "methane": 16.04, "ethylene": 28.05, "ethane": 30.07,
      "propylene": 42.08, "1-butene": 56.11}       # C3 and C4+ lumps as in the model
RECOVERY = 0.995
P_COLD_BAR = 30.0          # 32 bar discharge less the drying and chilling-train drop


def feed_from_inventory(y, acet):
    """Cold-box feed in kg per kg ethylene product, after acetylene hydrogenation.

    Follows the model: ethylene 1, ethane = recycle, hydrogen less the amount
    consumed in the converter; methane, C3 and C4+ pass through unchanged.
    """
    return {
        "hydrogen": acet["rawH2Kg"] - acet["h2ConsumedKg"],
        "methane": y["ch4"],
        "ethylene": acet["rawEthyleneKg"] + acet["ethyleneRecoveredKg"],
        "ethane": acet["rawEthaneKg"] + acet["ethaneMadeKg"],
        "propylene": y["c3"],
        "1-butene": y["c4plus"],
    }


def load_feeds():
    with open(os.path.join(DATA, "scenarios.json")) as fh:
        ref = json.load(fh)["baseline"]["gp_fired"]
    with open(os.path.join(DATA, "wang-downstream.json")) as fh:
        wang = json.load(fh)
    feeds = {
        "reference fired case (850 degC, 0.35 s)": {
            "mass": feed_from_inventory(ref["y"], ref["acetylene"]),
            "model_tCold_degC": ref["tCold"]},
        "Wang 2026, published Table 5 composition": {
            "mass": feed_from_inventory(wang["published_inventory"]["y"], wang["published"]["acetylene"]),
            "model_tCold_degC": wang["published"]["tCold"]},
    }
    # The GP-predicted inventory of the Wang case is not stored in wang-downstream.json;
    # dump_wang_gp_inventory.cjs writes it from the pinned engine.
    gp_path = os.path.join(HERE, "wang-gp-inventory.json")
    if os.path.exists(gp_path):
        with open(gp_path) as fh:
            gp = json.load(fh)
        feeds["Wang 2026, GP-predicted composition"] = {
            "mass": feed_from_inventory(gp["y"], gp["acetylene"]),
            "model_tCold_degC": gp["tCold"]}
    return feeds


def mole_fractions(mass):
    n = {k: mass[k] / MW[k] for k in NAMES}
    tot = sum(n.values())
    return [n[k] / tot for k in NAMES], tot


def correlation_tc(phi, r_e=RECOVERY):
    return -100.0 - 40.0 * math.log10(0.01 / (1.0 - r_e)) - 160.0 * (phi - 0.40)


def build_flasher(use_kij=True):
    consts, props = ChemicalConstantsPackage.from_IDs(NAMES)
    if use_kij:
        kijs = IPDB.get_ip_asymmetric_matrix("ChemSep PR", consts.CASs, "kij")
    else:
        kijs = [[0.0] * len(NAMES) for _ in NAMES]
    eos_kw = dict(Tcs=consts.Tcs, Pcs=consts.Pcs, omegas=consts.omegas, kijs=kijs)
    gas = CEOSGas(PRMIX, eos_kwargs=eos_kw, HeatCapacityGases=props.HeatCapacityGases)
    liq = CEOSLiquid(PRMIX, eos_kwargs=eos_kw, HeatCapacityGases=props.HeatCapacityGases)
    return FlashVL(consts, props, liquid=liq, gas=gas), kijs


I_E = NAMES.index("ethylene")


def ethylene_recovery(flasher, zs, T, P):
    res = flasher.flash(T=T, P=P, zs=zs)
    if res.gas is None:
        return 1.0, res
    if not res.liquids:
        return 0.0, res
    return 1.0 - res.VF * res.gas.zs[I_E] / zs[I_E], res


def solve_cold_end(flasher, zs, P, r_target=RECOVERY, lo=110.0, hi=273.0):
    T = brentq(lambda T: ethylene_recovery(flasher, zs, T, P)[0] - r_target, lo, hi, xtol=1e-3)
    return T, ethylene_recovery(flasher, zs, T, P)[1]


def describe(res):
    out = {"VF_mol": res.VF}
    if res.gas is not None:
        out["vapor_mol_frac"] = {n: round(v, 5) for n, v in zip(NAMES, res.gas.zs)}
    if res.liquids:
        out["liquid_mol_frac"] = {n: round(v, 5) for n, v in zip(NAMES, res.liquids[0].zs)}
    return out


def main():
    feeds = load_feeds()
    flasher_kij, kijs = build_flasher(True)
    flasher_0, _ = build_flasher(False)
    out = {"recovery": RECOVERY, "P_cold_bar": P_COLD_BAR,
           "kij_source": "ChemSep PR table in thermo.interaction_parameters.IPDB",
           "kij_matrix": {NAMES[i]: {NAMES[j]: kijs[i][j] for j in range(len(NAMES))}
                          for i in range(len(NAMES))},
           "feeds": {}}
    for label, f in feeds.items():
        zs, n_tot = mole_fractions(f["mass"])
        phi = zs[0] + zs[1]
        rec = {"feed_mass_kg_per_kg_ethylene": f["mass"],
               "feed_mol_frac": dict(zip(NAMES, [round(z, 5) for z in zs])),
               "feed_mol_per_kg_ethylene": n_tot * 1000.0,
               "phi_methane_plus_hydrogen": phi,
               "model_tCold_degC": f["model_tCold_degC"],
               "correlation_tc_degC_recomputed": correlation_tc(phi),
               "vle": {}}
        print(f"\n== {label}")
        print(f"   mol frac: " + ", ".join(f"{n} {z:.4f}" for n, z in zip(NAMES, zs)))
        print(f"   phi = {phi:.4f}; model t_c = {f['model_tCold_degC']:.1f} degC; "
              f"correlation recomputed = {correlation_tc(phi):.1f} degC")
        for key, flasher, P_bar in (("PR ChemSep kij, 30 bar", flasher_kij, 30.0),
                                    ("PR ChemSep kij, 32 bar", flasher_kij, 32.0),
                                    ("PR ChemSep kij, 25 bar", flasher_kij, 25.0),
                                    ("PR kij = 0, 30 bar", flasher_0, 30.0)):
            T, res = solve_cold_end(flasher, zs, P_bar * 1e5)
            rec["vle"][key] = {"P_bar": P_bar, "T_cold_end_degC": T - 273.15, **describe(res)}
            print(f"   {key:24s} T_cold = {T - 273.15:7.1f} degC   vapor/feed = {res.VF:.4f}   "
                  f"y_H2 = {res.gas.zs[0]:.3f}  y_CH4 = {res.gas.zs[1]:.3f}")
        r_m, res_m = ethylene_recovery(flasher_kij, zs, f["model_tCold_degC"] + 273.15, P_COLD_BAR * 1e5)
        rec["recovery_at_model_tCold"] = {"T_degC": f["model_tCold_degC"], "ethylene_recovery": r_m,
                                          **describe(res_m)}
        print(f"   at the model's t_c ({f['model_tCold_degC']:.1f} degC, {P_COLD_BAR:g} bar) one stage "
              f"recovers {100 * r_m:.2f} % of the ethylene")
        table = []
        for t in range(-60, -151, -10):
            r, res_t = ethylene_recovery(flasher_kij, zs, t + 273.15, P_COLD_BAR * 1e5)
            table.append({"T_degC": t, "ethylene_recovery": r, "VF_mol": res_t.VF,
                          "y_ethylene_vapor": res_t.gas.zs[I_E] if res_t.gas else 0.0})
        rec["recovery_vs_T_30bar"] = table
        out["feeds"][label] = rec

    path = os.path.join(HERE, "coldbox-vle-results.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("\nwrote", path)


if __name__ == "__main__":
    main()
