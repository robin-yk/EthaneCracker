"""Cascade refrigeration for the cold box with real-fluid properties.

Step 3 of the cold-box reassessment (2026-10-14). The engine converts duty to
work with w = q / (0.35 T_level / (T_amb - T_level)), i.e. a Carnot coefficient
of performance times a second-law efficiency of 0.35, at the levels -40 degC,
-100 degC and the cold end. This script replaces that rule with vapor-
compression cycles evaluated from CoolProp equations of state:

    propylene cycle   evaporates at (-40 degC service) - dT, condenses against
                      cooling water at T_amb + dT
    ethylene cycle    evaporates at (-100 degC service) - dT, condenses against
                      the propylene evaporator
    methane cycle     evaporates at (cold end) - dT, condenses against the
                      ethylene evaporator

Each cycle is computed single-stage and two-stage with a flash economizer
(intermediate pressure = geometric mean), compressor isentropic efficiency 0.75
(the engine's cracked-gas compressor value), saturated vapor at the evaporator
outlet, saturated liquid at the condenser outlet, isenthalpic expansion. Cascade
condenser loads are passed to the next-warmer cycle. The C2-splitter condenser
(243 K service) is also evaluated on the propylene cycle.

Duties by level come from coldbox-duty-results.json (Step 2).

Run from this folder after coldbox_duty.py:
    ~/.venvs/ethane-coldbox/bin/python refrigeration_cycles.py
Writes refrigeration-cycles-results.json next to this file.
"""
import json
import math
import os

from CoolProp.CoolProp import PropsSI

HERE = os.path.dirname(os.path.abspath(__file__))
DT = 5.0              # approach temperature in evaporators and condensers, K
ETA_S = 0.75          # compressor isentropic efficiency, as in the engine's compressor
T_AMB = 303.0         # engine ambient / heat rejection temperature, K
ETA2_ENGINE = 0.35
SPLITTER_T = 243.0    # K, engine C2-splitter condenser level


def sat(fluid, T, Q):
    return {"P": PropsSI("P", "T", T, "Q", Q, fluid), "H": PropsSI("H", "T", T, "Q", Q, fluid),
            "S": PropsSI("S", "T", T, "Q", Q, fluid)}


def compress(fluid, h_in, P_in, P_out, eta_s):
    s_in = PropsSI("S", "H", h_in, "P", P_in, fluid)
    h_is = PropsSI("H", "S", s_in, "P", P_out, fluid)
    return h_in + (h_is - h_in) / eta_s


def cop_single(fluid, T_evap, T_cond, eta_s=ETA_S):
    e, c = sat(fluid, T_evap, 1), sat(fluid, T_cond, 0)
    h2 = compress(fluid, e["H"], e["P"], c["P"], eta_s)
    q = e["H"] - c["H"]
    w = h2 - e["H"]
    return q / w, {"P_evap_bar": e["P"] / 1e5, "P_cond_bar": c["P"] / 1e5, "pressure_ratio": c["P"] / e["P"],
                   "T_discharge_degC": PropsSI("T", "H", h2, "P", c["P"], fluid) - 273.15}


def cop_two_stage(fluid, T_evap, T_cond, eta_s=ETA_S):
    e, c = sat(fluid, T_evap, 1), sat(fluid, T_cond, 0)
    P_i = math.sqrt(e["P"] * c["P"])
    h_fi, h_gi = PropsSI("H", "P", P_i, "Q", 0, fluid), PropsSI("H", "P", P_i, "Q", 1, fluid)
    x = (c["H"] - h_fi) / (h_gi - h_fi)            # vapor made in the economizer flash
    m_high = 1.0 / (1.0 - x)                        # per unit mass through the evaporator
    h2 = compress(fluid, e["H"], e["P"], P_i, eta_s)
    h3 = (h2 + (m_high - 1.0) * h_gi) / m_high      # mixing at intermediate pressure
    h4 = compress(fluid, h3, P_i, c["P"], eta_s)
    q = e["H"] - h_fi
    w = (h2 - e["H"]) + m_high * (h4 - h3)
    return q / w, {"P_int_bar": P_i / 1e5, "economizer_vapor_fraction": x,
                   "T_discharge_degC": PropsSI("T", "H", h4, "P", c["P"], fluid) - 273.15}


def carnot_cop_engine(T_level):
    return max(0.05, ETA2_ENGINE * T_level / (T_AMB - T_level))


def cascade_work(duties, cops):
    """duties: dict with keys -40, -100, cold_end (kJ/kg); cops: dict of COPs per cycle.
    Returns work per cycle and total, kJ/kg."""
    q_m = duties["cold_end"]
    w_m = q_m / cops["methane"]
    q_e = duties["-100"] + q_m + w_m
    w_e = q_e / cops["ethylene"]
    q_p = duties["-40"] + q_e + w_e
    w_p = q_p / cops["propylene"]
    return {"methane": w_m, "ethylene": w_e, "propylene": w_p, "total": w_m + w_e + w_p,
            "propylene_evaporator_load": q_p}


def main():
    with open(os.path.join(HERE, "coldbox-duty-results.json")) as fh:
        duty = json.load(fh)
    out = {"dT_approach_K": DT, "eta_isentropic": ETA_S, "T_amb_K": T_AMB, "cycles": {}, "feeds": {}}

    # cycle temperatures from the reference-case cold end
    ref = duty["feeds"]["reference fired case (850 degC, 0.35 s)"]
    t_cold = ref["cold_end_degC"]
    levels = {"propylene": {"fluid": "Propylene", "T_evap": 233.15 - DT, "T_cond": T_AMB + DT},
              "ethylene": {"fluid": "Ethylene", "T_evap": 173.15 - DT, "T_cond": 233.15 - DT + DT},
              "methane": {"fluid": "Methane", "T_evap": t_cold + 273.15 - DT, "T_cond": 173.15 - DT + DT}}
    # ethylene condenses against the propylene evaporator (T_evap,p + dT); methane against the
    # ethylene evaporator (T_evap,e + dT)
    levels["ethylene"]["T_cond"] = levels["propylene"]["T_evap"] + DT
    levels["methane"]["T_cond"] = levels["ethylene"]["T_evap"] + DT
    cops1, cops2 = {}, {}
    for name, L in levels.items():
        c1, d1 = cop_single(L["fluid"], L["T_evap"], L["T_cond"])
        c2, d2 = cop_two_stage(L["fluid"], L["T_evap"], L["T_cond"])
        T_service = L["T_evap"] + DT
        T_crit = PropsSI("Tcrit", L["fluid"])
        cops1[name], cops2[name] = c1, c2
        out["cycles"][name] = {"fluid": L["fluid"], "T_evap_degC": L["T_evap"] - 273.15,
                               "T_cond_degC": L["T_cond"] - 273.15, "T_crit_degC": T_crit - 273.15,
                               "COP_single_stage": c1, "COP_two_stage_economizer": c2,
                               "carnot_COP_between_cycle_temperatures": L["T_evap"] / (L["T_cond"] - L["T_evap"]),
                               "engine_COP_at_service_level": carnot_cop_engine(T_service),
                               "single": d1, "two_stage": d2}
        print(f"{name:10s} {L['fluid']:10s} evap {L['T_evap'] - 273.15:7.1f} C  cond {L['T_cond'] - 273.15:6.1f} C  "
              f"(Tcrit {T_crit - 273.15:6.1f})  COP 1-stage {c1:.3f}  2-stage {c2:.3f}  "
              f"Carnot {L['T_evap'] / (L['T_cond'] - L['T_evap']):.3f}   "
              f"engine COP at service level {carnot_cop_engine(T_service):.3f}")

    # C2 splitter condenser on the propylene cycle at (243 K - dT)
    cs1, _ = cop_single("Propylene", SPLITTER_T - DT, T_AMB + DT)
    cs2, _ = cop_two_stage("Propylene", SPLITTER_T - DT, T_AMB + DT)
    out["splitter_condenser"] = {"T_service_K": SPLITTER_T, "COP_single": cs1, "COP_two_stage": cs2,
                                 "engine_COP": carnot_cop_engine(SPLITTER_T)}
    print(f"\nC2 splitter condenser at {SPLITTER_T - 273.15:.0f} C: propylene COP 1-stage {cs1:.3f}, "
          f"2-stage {cs2:.3f}, engine {carnot_cop_engine(SPLITTER_T):.3f}")

    for label, f in duty["feeds"].items():
        q = f["duty_by_level_kJ_per_kg"]
        q_cred = f["with_condensate_credit"]["duty_by_level_kJ_per_kg"]
        res = {}
        for tag, cops in (("single_stage", cops1), ("two_stage", cops2)):
            res[tag] = {"tail_gas_recuperation": cascade_work(q, cops),
                        "with_condensate_credit": cascade_work(q_cred, cops)}
        # effective second-law efficiency: Carnot work at the service levels / actual work
        T_levels = {"-40": 233.15, "-100": 173.15, "cold_end": f["cold_end_degC"] + 273.15}
        w_carnot = sum(q[k] * (T_AMB - T_levels[k]) / T_levels[k] for k in q)
        res["carnot_work_at_service_levels_kJ_per_kg"] = w_carnot
        res["eta2_effective"] = {tag: w_carnot / res[tag]["tail_gas_recuperation"]["total"]
                                 for tag in ("single_stage", "two_stage")}
        res["engine_w_ref_kJ_per_kg"] = f["engine"]["w_ref_kJ_per_kg"]
        res["step2_w_ref_engine_rule_kJ_per_kg"] = f["w_ref_vle_engine_efficiency_kJ_per_kg"]
        out["feeds"][label] = res
        print(f"\n== {label}")
        print(f"   engine w_ref {f['engine']['w_ref_kJ_per_kg']:6.0f};  VLE duty with engine rule "
              f"{f['w_ref_vle_engine_efficiency_kJ_per_kg']:6.0f} kJ/kg")
        for tag in ("single_stage", "two_stage"):
            a, b = res[tag]["tail_gas_recuperation"], res[tag]["with_condensate_credit"]
            print(f"   cascade {tag:12s}: w_ref {a['total']:6.0f} kJ/kg "
                  f"(propylene {a['propylene']:.0f}, ethylene {a['ethylene']:.0f}, methane {a['methane']:.0f}); "
                  f"with condensate credit {b['total']:6.0f}; effective eta2 {res['eta2_effective'][tag]:.3f}")

    path = os.path.join(HERE, "refrigeration-cycles-results.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("\nwrote", path)


if __name__ == "__main__":
    main()
