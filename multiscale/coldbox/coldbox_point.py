"""One cold-box evaluation for a given feed: cold end, duties by level, tail gas.

Same physics as coldbox_vle.py (Step 1) and coldbox_duty.py (Step 2), packaged as
a function for the training-data generator. `step_K` sets the cooling-curve
resolution; 1 K reproduces Step 2, 2 K is used for training.
"""
import numpy as np

from coldbox_duty import DT_MIN, LEVELS_C, T_IN_C, T_LIQ_RETURN_C, enthalpy_kj_per_kg
from coldbox_vle import MW, NAMES, P_COLD_BAR, mole_fractions, solve_cold_end

I_E = NAMES.index("ethylene")


def coldbox_point(mass, flasher, step_K=1.0, P_bar=P_COLD_BAR):
    """mass: kg per kg ethylene for NAMES. Returns a dict of results (kJ per kg ethylene)."""
    P = P_bar * 1e5
    zs, n_tot = mole_fractions(mass)
    n_mol = n_tot * 1000.0
    T_c, res_c = solve_cold_end(flasher, zs, P)
    t_c = T_c - 273.15
    y_tail = list(res_c.gas.zs)
    x_liq = list(res_c.liquids[0].zs)
    n_tail = res_c.VF * n_mol
    n_liq = (1.0 - res_c.VF) * n_mol

    T_grid = np.arange(T_IN_C, t_c - 1e-9, -step_K)
    T_grid = np.append(T_grid, t_c)
    H_feed = np.array([enthalpy_kj_per_kg(flasher, zs, T + 273.15, P, n_mol)[0] for T in T_grid])
    H_tail = np.array([enthalpy_kj_per_kg(flasher, y_tail, T + 273.15, P, n_tail)[0] for T in T_grid])
    H_liq = np.array([enthalpy_kj_per_kg(flasher, x_liq, T + 273.15, P, n_liq)[0] for T in T_grid])
    T_out = T_IN_C - DT_MIN
    H_tail_out = enthalpy_kj_per_kg(flasher, y_tail, T_out + 273.15, P, n_tail)[0]
    Q_total = H_feed[0] - H_feed[-1]

    q_feed = -np.diff(H_feed)
    T_mid = 0.5 * (T_grid[:-1] + T_grid[1:])
    Tr, Htr, Hlr = T_grid[::-1], H_tail[::-1], H_liq[::-1]

    def stream_q(H_rev, T_return):
        def H_at(T):
            return np.interp(T, Tr, H_rev)
        q = np.zeros_like(q_feed)
        for k in range(len(q_feed)):
            if T_grid[k] - DT_MIN > t_c:
                hi = min(T_return, T_grid[k] - DT_MIN)
                lo = min(T_return, T_grid[k + 1] - DT_MIN)
                q[k] = max(0.0, H_at(hi) - H_at(lo))
        return q

    q_gas = np.minimum(stream_q(Htr, T_out), q_feed)
    q_liq = np.minimum(stream_q(Hlr, T_LIQ_RETURN_C), q_feed - q_gas)

    def split(q_net):
        d = {"-40": 0.0, "-100": 0.0, "cold_end": 0.0}
        for T, q in zip(T_mid, q_net):
            if T - DT_MIN >= LEVELS_C[0]:
                d["-40"] += q
            elif T - DT_MIN >= LEVELS_C[1]:
                d["-100"] += q
            else:
                d["cold_end"] += q
        return d

    q_nc = q_feed - q_gas            # tail-gas recuperation only
    q_cc = q_nc - q_liq              # plus condensate cold used
    d_nc, d_cc = split(q_nc), split(q_cc)
    return {
        "T_cold_K": T_c,
        "t_cold_degC": t_c,
        "x": dict(zip(NAMES, zs)),
        "feed_kg": sum(mass.values()),
        "tail_gas_kg": sum(y * n_tail / 1000.0 * MW[n] for n, y in zip(NAMES, y_tail)),
        "tail_gas_y": dict(zip(NAMES, y_tail)),
        "Q_total": Q_total,
        "Q_rec_gas": float(q_gas.sum()),
        "Q_rec_liq": float(q_liq.sum()),
        "q40_cc": d_cc["-40"], "q100_cc": d_cc["-100"], "qcold_cc": d_cc["cold_end"],
        "q40_nc": d_nc["-40"], "q100_nc": d_nc["-100"], "qcold_nc": d_nc["cold_end"],
    }
