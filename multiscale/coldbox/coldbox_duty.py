"""Cold-box heat balance from vapor-liquid equilibrium, with tail-gas recuperation.

Step 2 of the cold-box reassessment (2026-10-14). The published engine uses

    q_c = 2.2 m_g (30 - t_c) + 350 (1 + m_recycle + m_C2H2 + m_C3 + m_C4+)   [kJ/kg ethylene]

and no credit for the cold returned by the rewarming tail gas. This script
computes the same quantity from Peng-Robinson enthalpies:

  Q_total  enthalpy drop of the cold-box feed from the inlet temperature (vapor,
           30 bar) to the two-phase state at the cold end T_c of Step 1
  Q_rec    enthalpy gained by the tail gas (vapor at T_c) rewarming to
           T_in - dT_min against the feed; optionally also by the condensate
           rewarming to -30 degC (the C2-splitter condenser level)
  Q_ref    = Q_total - Q_rec, the duty the refrigeration system must supply,
           split by temperature level from the cooling and heating curves

The refrigeration work is then evaluated with the engine's own efficiency rule
(Carnot COP times eta_2 = 0.35, ambient 303 K) so that only the duty and its
temperature distribution change.

Run from this folder after coldbox_vle.py:
    ~/.venvs/ethane-coldbox/bin/python coldbox_duty.py
Writes coldbox-duty-results.json next to this file.
"""
import json
import os

import numpy as np

from coldbox_vle import (HERE, MW, NAMES, P_COLD_BAR, build_flasher, load_feeds, mole_fractions,
                         solve_cold_end)

T_IN_C = 30.0            # feed enters the cold box at 30 degC, the engine's sensible-heat datum
DT_MIN = 5.0             # minimum approach in the plate-fin core, K
T_LIQ_RETURN_C = -30.0   # condensate rewarmed to the C2-splitter condenser level, degC
LEVELS_C = [-40.0, -100.0]   # engine refrigeration levels; the third is the cold end itself
ETA2, T_AMB = 0.35, 303.0
I_E = NAMES.index("ethylene")


def enthalpy_kj_per_kg(flasher, zs, T, P, n_tot_mol):
    """Mixture enthalpy, kJ per kg ethylene product (n_tot_mol = feed mol per kg ethylene)."""
    res = flasher.flash(T=T, P=P, zs=zs)
    return res.H() * n_tot_mol / 1000.0, res


def engine_duty(mass, t_c):
    m_g = sum(mass.values())
    cond = mass["ethylene"] + mass["ethane"] + mass["propylene"] + mass["1-butene"]
    return 2.2 * m_g * (T_IN_C - t_c) + 350.0 * cond


def engine_work(duties_by_level):
    """Engine rule: w = sum q_j / max(0.05, eta2 T_j/(T_a - T_j))."""
    w = 0.0
    for T_k, q in duties_by_level:
        w += q / max(0.05, ETA2 * T_k / (T_AMB - T_k))
    return w


def main():
    feeds = load_feeds()
    flasher, _ = build_flasher(True)
    P = P_COLD_BAR * 1e5
    out = {"P_cold_bar": P_COLD_BAR, "T_in_degC": T_IN_C, "dT_min_K": DT_MIN,
           "liquid_return_degC": T_LIQ_RETURN_C, "eta2": ETA2, "T_amb_K": T_AMB, "feeds": {}}

    for label, f in feeds.items():
        mass = f["mass"]
        zs, n_tot = mole_fractions(mass)
        n_mol = n_tot * 1000.0                      # mol per kg ethylene
        T_c, res_c = solve_cold_end(flasher, zs, P)
        t_c = T_c - 273.15
        y_tail = list(res_c.gas.zs)
        x_liq = list(res_c.liquids[0].zs)
        n_tail = res_c.VF * n_mol
        n_liq = (1.0 - res_c.VF) * n_mol

        # cooling curve of the feed (two-phase below the dew point)
        T_grid = np.arange(T_IN_C, t_c - 1e-9, -1.0)
        T_grid = np.append(T_grid, t_c)
        H_feed = np.array([enthalpy_kj_per_kg(flasher, zs, T + 273.15, P, n_mol)[0] for T in T_grid])
        Q_total = H_feed[0] - H_feed[-1]

        # heating curve of the tail gas, T_c -> T_in - dT_min
        T_out = T_IN_C - DT_MIN
        H_tail = np.array([enthalpy_kj_per_kg(flasher, y_tail, T + 273.15, P, n_tail)[0]
                           for T in T_grid])
        H_tail_out = enthalpy_kj_per_kg(flasher, y_tail, T_out + 273.15, P, n_tail)[0]
        Q_rec_gas = H_tail_out - H_tail[-1]

        # condensate rewarming T_c -> -30 degC (optional credit)
        H_liq_c = enthalpy_kj_per_kg(flasher, x_liq, T_c, P, n_liq)[0]
        H_liq_ret = enthalpy_kj_per_kg(flasher, x_liq, T_LIQ_RETURN_C + 273.15, P, n_liq)[0]
        Q_rec_liq = H_liq_ret - H_liq_c

        # interval balance: feed cooling in [T-1, T] minus tail gas warming in the
        # interval shifted up by dT_min (the gas at T warms the feed at T + dT_min)
        q_feed = -np.diff(H_feed)                   # kJ released per interval, index k: T_grid[k] -> T_grid[k+1]
        T_mid = 0.5 * (T_grid[:-1] + T_grid[1:])
        def tail_H(T):
            return np.interp(T, T_grid[::-1], H_tail[::-1])
        q_gas = np.array([max(0.0, tail_H(min(T_out, T_grid[k] - DT_MIN)) -
                              tail_H(min(T_out, T_grid[k + 1] - DT_MIN)))
                          if T_grid[k] - DT_MIN > t_c else 0.0
                          for k in range(len(q_feed))])
        q_gas = np.minimum(q_gas, q_feed)
        # condensate as a second cold stream, T_c -> T_LIQ_RETURN_C, same shift
        H_liq = np.array([enthalpy_kj_per_kg(flasher, x_liq, T + 273.15, P, n_liq)[0]
                          for T in T_grid])
        def liq_H(T):
            return np.interp(T, T_grid[::-1], H_liq[::-1])
        q_liq = np.array([max(0.0, liq_H(min(T_LIQ_RETURN_C, T_grid[k] - DT_MIN)) -
                              liq_H(min(T_LIQ_RETURN_C, T_grid[k + 1] - DT_MIN)))
                          if T_grid[k] - DT_MIN > t_c else 0.0
                          for k in range(len(q_feed))])
        q_liq = np.minimum(q_liq, q_feed - q_gas)

        def split_levels(q_net):
            # assign each interval's net duty to the warmest refrigerant level at or below T_mid - dT_min
            duty = {"-40": 0.0, "-100": 0.0, "cold_end": 0.0}
            for T, q in zip(T_mid, q_net):
                if T - DT_MIN >= LEVELS_C[0]:
                    duty["-40"] += q
                elif T - DT_MIN >= LEVELS_C[1]:
                    duty["-100"] += q
                else:
                    duty["cold_end"] += q
            w = engine_work([(LEVELS_C[0] + 273.15, duty["-40"]), (LEVELS_C[1] + 273.15, duty["-100"]),
                             (T_c, duty["cold_end"])])
            return duty, w

        q_net = q_feed - q_gas
        Q_ref = float(q_net.sum())
        assert abs(Q_ref - (Q_total - q_gas.sum())) < 1e-6
        duty, w_vle = split_levels(q_net)
        duty_liq, w_vle_liq = split_levels(q_net - q_liq)
        Q_ref_liq = float((q_net - q_liq).sum())
        # same duty without the recuperation credit, and the engine's own numbers
        q_eng = engine_duty(mass, f["model_tCold_degC"])
        a_eng = (0.55, 0.30, 0.15)
        T_eng = [233.15, 173.15, f["model_tCold_degC"] + 273.15]
        w_eng = engine_work(list(zip(T_eng, [a * q_eng for a in a_eng])))
        rec = {
            "cold_end_degC": t_c,
            "feed_kg_per_kg_ethylene": sum(mass.values()),
            "tail_gas_mol_frac": dict(zip(NAMES, [round(v, 5) for v in y_tail])),
            "tail_gas_kg_per_kg_ethylene": sum(y * n_tail / 1000.0 * MW[n] for n, y in zip(NAMES, y_tail)),
            "Q_total_kJ_per_kg": Q_total,
            "Q_rec_tail_gas_kJ_per_kg": Q_rec_gas,
            "Q_rec_condensate_to_-30C_kJ_per_kg": Q_rec_liq,
            "Q_ref_kJ_per_kg": Q_ref,
            "Q_ref_with_condensate_credit_kJ_per_kg": Q_ref_liq,
            "duty_by_level_kJ_per_kg": duty,
            "duty_fractions": {k: v / Q_ref for k, v in duty.items()},
            "w_ref_vle_engine_efficiency_kJ_per_kg": w_vle,
            "with_condensate_credit": {"duty_by_level_kJ_per_kg": duty_liq,
                                       "duty_fractions": {k: v / Q_ref_liq for k, v in duty_liq.items()},
                                       "w_ref_kJ_per_kg": w_vle_liq},
            "engine": {"t_c_degC": f["model_tCold_degC"], "q_c_kJ_per_kg": q_eng,
                       "duty_fractions": a_eng, "w_ref_kJ_per_kg": w_eng},
            "cooling_curve": [{"T_degC": float(T), "H_feed_kJ_per_kg": float(h), "H_tail_kJ_per_kg": float(g)}
                              for T, h, g in zip(T_grid[::10], H_feed[::10], H_tail[::10])],
        }
        out["feeds"][label] = rec
        print(f"\n== {label}")
        print(f"   cold end {t_c:.1f} degC; feed {rec['feed_kg_per_kg_ethylene']:.3f} kg, "
              f"tail gas {rec['tail_gas_kg_per_kg_ethylene']:.4f} kg per kg ethylene")
        print(f"   Q_total {Q_total:7.0f}   Q_rec(tail gas) {Q_rec_gas:6.0f}   Q_ref {Q_ref:7.0f}   "
              f"[+ condensate credit to -30 C: {Q_rec_liq:5.0f} -> Q_ref {Q_ref_liq:6.0f}, "
              f"w_ref {w_vle_liq:5.0f}, levels {duty_liq['-40'] / Q_ref_liq:.2f}/"
              f"{duty_liq['-100'] / Q_ref_liq:.2f}/{duty_liq['cold_end'] / Q_ref_liq:.2f}]  kJ/kg")
        print(f"   duty by level  -40 C {duty['-40']:6.0f} ({duty['-40'] / Q_ref:.2f})   "
              f"-100 C {duty['-100']:6.0f} ({duty['-100'] / Q_ref:.2f})   "
              f"cold end {duty['cold_end']:6.0f} ({duty['cold_end'] / Q_ref:.2f})")
        print(f"   w_ref: VLE duty with engine efficiency {w_vle:6.0f} kJ/kg   "
              f"engine {w_eng:6.0f} kJ/kg (q_c {q_eng:.0f} at {f['model_tCold_degC']:.1f} C)")

    path = os.path.join(HERE, "coldbox-duty-results.json")
    with open(path, "w") as fh:
        json.dump(out, fh, indent=1)
    print("\nwrote", path)


if __name__ == "__main__":
    main()
