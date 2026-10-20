/* =====================================================================================================
   ETHANE CRACKER PROCESS AND COST MODEL
   Basis: 1 kg of polymer-grade ethylene product. Results are per tonne (t) of ethylene.

   This module calculates one steady-state ethane cracker from the coil to the product, then the cost and
   the carbon intensity. The blocks are in process order:
     1  Reaction in the cracking coil (AramcoMech 3.0 kinetics through a Gaussian-process surrogate)
     2  Acetylene hydrogenation and the product basis (coil ethane, fresh ethane, recycle ethane)
     3  Heat supply: fired furnace (radiant and convection sections) or electric heating
     4  Coil heat flux and tube metal temperature
     5  Cracked-gas compression
     6  Cold box (Peng-Robinson flash) and refrigeration
     7  C2 splitter, deethanizer, depropanizer, debutanizer
     8  Run length and capital
     9  Production cost
    10  Carbon intensity
   Each block gives its equations in words and symbols, and each constant has a unit, a range and a source.
   Abbreviations: COT = coil outlet temperature; TLE = transfer-line exchanger; LHV = lower heating value;
   GP = Gaussian process; FUG = Fenske-Underwood-Gilliland; TMT = tube metal temperature.
   ===================================================================================================== */
const EthaneCrackerModel = (function () {
'use strict';

/* ---------- Molar masses, kg/kmol ---------- */
const MOLAR_MASS = { ethane: 30.07, ethylene: 28.05, methane: 16.04, hydrogen: 2.016, acetylene: 26.038,
  c3: 42.08, c4: 56.11, carbon: 12.011, water: 18.015 };
const GAS_CONSTANT = 8.314462618;               // J/(mol K)
const STOICHIOMETRIC_ETHANE_PER_ETHYLENE = MOLAR_MASS.ethane / MOLAR_MASS.ethylene;   // 1.0719 kg/kg at 100 % selectivity

/* ---------- Default inputs. The screen can change every one of them. ---------- */
const DEFAULT_INPUTS = {
  heatSource: 'fired',            // 'fired' or 'electric'
  firedHeatModel: 'radiant',      // 'radiant' = radiant and convection balance; 'fixed' = fixed efficiency
  coilOutletTemperature_C: 850,   // degC, GP range 750-1000
  residenceTime_s: 0.35,          // s, GP range 0.02-1.5
  steamToEthane_kg_per_kg: 0.35,  // kg dilution steam per kg ethane, GP range 0-0.7
  coilPressure_bar: 1.5,          // bar, GP range 1-5
  heatingExponent: 1,             // -, gas temperature T = 650 + (COT-650)(t/tau)^n, GP range 0.45-4
  plantCapacity_kt_per_y: 610,    // kt/y ethylene, Mittal et al. 2025 SI
  ethanePrice_USD_per_t: 200,     // Mittal et al. 2025 SI
  naturalGasPrice_USD_per_GJ: 4,  // LHV, EIA 2024 US industrial
  electricityPrice_USD_per_kWh: 0.07,   // scenario; EIA 2024 Texas 0.061, Louisiana 0.056
  exportSteamPrice_USD_per_GJ: 4.4,     // natural-gas price / 0.90 boiler efficiency (Towler and Sinnott 2013, Eq. 3.1)
  c3PlusPrice_USD_per_t: 550,     // LPG price, Mittal et al. 2025 SI
  fuelGasPriceFactor: 0.5,        // - of the natural-gas price per GJ; H2-rich fuel gas is off-specification (assumption)
  fuelGasUse: 'sell',             // surplus fuel gas: 'sell' (credit) or 'burn' (no credit)
  gridEmissionFactor_kg_per_kWh: 0.36,  // kg CO2e/kWh, US 2023 delivered average
  ethaneUpstreamEmission_kg_per_kg: 0.50,   // kg CO2e/kg ethane, scenario
  firedEfficiencyFixed_percent: 60,     // %, used only with firedHeatModel 'fixed'; Towler and Sinnott 2022: about 0.6 for radiant-only heating
  electricEfficiency_percent: 95,       // %, Mittal et al. 2025 SI
  capitalChargeFactor_per_y: 0.10,      // 1/y, Mittal et al. 2025 SI
  labor_MUSD_per_y: 5                   // Mittal et al. 2025 SI
};

/* ---------- Fixed design values ---------- */
const DESIGN = {
  coilInletTemperature_C: 650,          // degC, radiant-coil inlet (crossover) in the GP training calculations
  feedPreheatStart_C: 150,              // degC, feed temperature before the convection section
  ethaneHeatCapacity_kJ_per_kgK: 3.0,   // mean 150-850 degC
  steamHeatCapacity_kJ_per_kgK: 2.3,    // mean 150-850 degC
  tleRecoveryFraction: 0.70,            // - of the effluent sensible heat raised as HP steam in the TLE, range 0.5-0.9 (assumption)
  dilutionSteamLatentHeat_kJ_per_kg: 2100,  // steam tables, about 5 barg
  dilutionSteamHeatGrade: 0.45,         // - of the export-steam price for low-grade generator heat, range 0.3-0.7 (assumption)
  coolingWaterCost_USD_per_GJ: 0.40,    // Seider et al. utility cost
  methaneLHV_MJ_per_kg: 50, hydrogenLHV_MJ_per_kg: 120, ethyleneLHV_MJ_per_kg: 47.2,
  ethyleneRecovery: 0.995,              // - of the ethylene that the cold box recovers; the rest goes to the fuel gas
  ethylenePurity: 0.999,                // mol fraction, polymer grade
  acetyleneTarget_ppm: 5,               // mol ppm acetylene in the ethylene product (EPA ethylene-process description)
  acetyleneToEthyleneSelectivity: 0.90, // - of hydrogenated acetylene that becomes ethylene; the rest becomes ethane
  compressorDischarge_bar: 32,          // bar
  compressorSuction_bar: 1.5,           // bar
  compressorStages: 4,
  compressorHeatCapacityRatio: 1.32,    // gamma of cracked gas
  compressorSuctionTemperature_K: 313,
  compressorIsentropicEfficiency: 0.75,
  coldBoxPressure_Pa: 30e5,             // 32 bar discharge less the drying and chilling-train pressure drop
  coldBoxApproach_K: 5,                 // plate-fin exchanger approach
  coldBoxFeedTemperature_K: 303.15, fuelGasReturnTemperature_K: 298.15, condensateReturnTemperature_K: 243.15,
  refrigerationLevelLimits_K: [238.15, 178.15],   // below 238 K the ethylene cycle serves, below 178 K the methane cycle
  // Coefficients of performance of two-stage economized cycles, CoolProp, 5 K approach, 30 degC cooling water, eta_is 0.75
  copPropylene: 1.693, copEthylene: 1.453, copMethane: 2.879, copC2SplitterCondenser: 2.067,
  c2SplitterLatentHeat_kJ_per_kg: 280,  // ethylene latent heat at the C2-splitter pressure
  runLengthReference_d: 60, decoking_d: 1.5
};

/* ---------- 1. REACTION: Gaussian-process surrogate of AramcoMech 3.0 in Cantera ----------
   Inputs x = [COT, log10(tau), steam/ethane, pressure, heating exponent], scaled to [0, 1].
   Squared-exponential kernel k_i = exp(-0.5 sum_j ((x_j - x_ij)/l_j)^2) over the 640 training points.
   Latent mean z = y_mean + y_std (k . alpha). Outputs on a logit or log scale are transformed back.
   Posterior SD: sigma = sqrt(1 - k K^-1 k) y_std (d output / d z) sigma_scale.
   Outputs: ethane conversion X, ethylene mol selectivity, mass yields (kg per kg coil ethane) of
   C2H4, CH4, H2, C2H2, C2H6, C3, C4+, and the coil enthalpy rise from 650 degC (MJ per kg ethane). */
let gpParameters = null, gpValidation = null, gpStatus = { status: 'FAILED', message: 'GP not loaded' };
function loadGP(parameters, validation) {
  if (!parameters || parameters.schema !== 'ethane-cantera-shared-rbf-gp-v3') throw new Error('GP FAILED: unknown parameter schema');
  gpParameters = parameters; gpValidation = validation;
  gpStatus = { status: 'OK', message: 'GP loaded: ' + parameters.training_points + ' Cantera training points' };
}
function predictReaction(inputs) {
  const m = gpParameters;
  const raw = [inputs.coilOutletTemperature_C, Math.log10(inputs.residenceTime_s), inputs.steamToEthane_kg_per_kg,
    inputs.coilPressure_bar, inputs.heatingExponent];
  const x = raw.map((v, j) => (v - m.x_min[j]) / (m.x_max[j] - m.x_min[j]));
  const n = m.x_train.length, k = new Array(n);
  for (let i = 0; i < n; i++) {
    let q = 0;
    for (let j = 0; j < x.length; j++) { const d = (x[j] - m.x_train[i][j]) / m.length_scale[j]; q += d * d; }
    k[i] = Math.exp(-0.5 * q);
  }
  let kKk = 0;
  for (let i = 0; i < n; i++) { let s = 0; const row = m.k_inv[i]; for (let j = 0; j < n; j++) s += row[j] * k[j]; kKk += k[i] * s; }
  const sigmaStandard = Math.sqrt(Math.max(0, 1 - kKk));
  const mean = {}, sd = {};
  for (let o = 0; o < m.outputs.length; o++) {
    let zs = 0; for (let i = 0; i < n; i++) zs += k[i] * m.alpha[i][o];
    const z = m.y_mean[o] + m.y_std[o] * zs, t = m.output_transforms[o];
    let value, derivative;
    if (t.kind === 'logit') { value = z >= 0 ? 1 / (1 + Math.exp(-z)) : Math.exp(z) / (1 + Math.exp(z)); derivative = value * (1 - value); }
    else { value = Math.max(0, Math.exp(z) - t.epsilon); derivative = Math.exp(z); }
    mean[m.outputs[o]] = value;
    sd[m.outputs[o]] = sigmaStandard * m.y_std[o] * derivative * (m.sigma_scale ? m.sigma_scale[o] : 1);
  }
  const outside = [];
  raw.forEach((v, j) => { if (v < m.domain_min[j] || v > m.domain_max[j]) outside.push(m.inputs[j]); });
  return { mean, sd, outsideTrainingRange: outside };
}
/* Direct composition: when set, block 1 uses this composition in place of the GP (shadow prices). */
let directComposition = null;

/* C5+ share of the GP C4+ lump: f = 1 - exp(-(y/0.11223)^1.0257), y = C4+ kg per kg coil ethane.
   Fit to 225 direct Cantera calculations at 850-900 degC (share RMSE 0.011); y range 0.0092-0.171. */
function c5PlusShare(c4PlusYield) { return 1 - Math.exp(-Math.pow(Math.max(c4PlusYield, 0) / 0.11223, 1.0257)); }

/* ---------- 3. FIRED FURNACE: combustion and flue-gas enthalpy ----------
   Fuel gas (CH4, H2, lost C2H4) burns first, then natural gas (CH4). Air excess 10 %.
   eta_radiant = 1 - H_flue(T_bridgewall)/LHV : the well-stirred firebox gas leaves the radiant section at the
   bridgewall temperature. eta_overall = 1 - H_flue(T_stack)/LHV - casing loss. */
const FURNACE = {
  excessAirFraction: 0.10,          // -, range 0.05-0.20, gas-fired heater practice (assumption)
  airTemperature_C: 25,             // degC, no air preheat (assumption)
  bridgewallTemperature_C: 1100,    // degC, range 1000-1250; flue gas leaves the radiant zone at about 1100 degC (US 11,913,362)
  stackTemperature_C: 130,          // degC, range 110-180 (assumption)
  casingLossFraction: 0.02,         // - of fuel LHV, range 0.01-0.03 (assumption)
  coilInsideDiameter_m: 0.0381,     // m, 1.5 in, US 2025/0277154 A1 Table 1
  coilVolumePerCoil_m3: 0.0146,     // m3, US 2025/0277154 A1 Table 1, used to count coils
  // Tube metal temperature: TMT_max = COT + peakFluxFactor * mean flux / filmConductance.
  // Both values come from the commercial Millisecond Furnace of US 2025/0277154 A1 Tables 1-2
  // (882 degC, 0.25 s, steam/ethane 0.5, 1.7 bar; outside wall 981 degC mean, 1117 degC maximum).
  filmConductance_W_per_m2K: 210.8, peakFluxFactor: 1.2535,
  tubeMetalLimit_C: 1150,           // degC, range 1100-1150 austenitic alloy (US 8,747,765 B2); the commercial MSF runs at 1117 degC
  referenceCoilArea_m2: 4710        // m2, coil area that carries the reference furnace capital share at 610 kt/y
};
const NASA7 = {   // [T_mid, high-range a1..a7, low-range a1..a7], GRI-Mech 3.0
  CO2: [1000, 3.85746029, 4.41437026e-3, -2.21481404e-6, 5.23490188e-10, -4.72084164e-14, -48759.166, 2.27163806, 2.35677352, 8.98459677e-3, -7.12356269e-6, 2.45919022e-9, -1.43699548e-13, -48371.9697, 9.90105222],
  H2O: [1000, 3.03399249, 2.17691804e-3, -1.64072518e-7, -9.7041987e-11, 1.68200992e-14, -30004.2971, 4.9667701, 4.19864056, -2.0364341e-3, 6.52040211e-6, -5.48797062e-9, 1.77197817e-12, -30293.7267, -0.849032208],
  N2: [1000, 2.92664, 1.4879768e-3, -5.68476e-7, 1.0097038e-10, -6.753351e-15, -922.7977, 5.980528, 3.298677, 1.4082404e-3, -3.963222e-6, 5.641515e-9, -2.444854e-12, -1020.8999, 3.950372],
  O2: [1000, 3.28253784, 1.48308754e-3, -7.57966669e-7, 2.09470555e-10, -2.16717794e-14, -1088.45772, 5.45323129, 3.78245636, -2.99673416e-3, 9.84730201e-6, -9.68129509e-9, 3.24372837e-12, -1063.94356, 3.65767573]
};
function sensibleEnthalpy_J_per_mol(species, T_K) {      // h(T) - h(298.15 K)
  const c = NASA7[species], h = t => { const a = t > c[0] ? c.slice(1, 8) : c.slice(8, 15);
    return GAS_CONSTANT * t * (a[0] + a[1] * t / 2 + a[2] * t * t / 3 + a[3] * t * t * t / 4 + a[4] * t * t * t * t / 5 + a[5] / t); };
  return h(T_K) - h(298.15);
}
/* Flue-gas sensible enthalpy above the air temperature, per kJ of fuel LHV. Fuel given as LHV fractions. */
function flueGasEnthalpyPerFuelLHV(fuelFraction, T_K) {
  const LHV_kJ_per_mol = { ch4: 802.3, h2: 241.8, c2h4: 1323.0 }, O2 = { ch4: 2, h2: 0.5, c2h4: 3 },
        CO2 = { ch4: 1, h2: 0, c2h4: 2 }, H2O = { ch4: 2, h2: 1, c2h4: 2 };
  let nO2 = 0, nCO2 = 0, nH2O = 0;
  for (const s of ['ch4', 'h2', 'c2h4']) { const mol = (fuelFraction[s] || 0) / LHV_kJ_per_mol[s]; nO2 += mol * O2[s]; nCO2 += mol * CO2[s]; nH2O += mol * H2O[s]; }
  const ex = FURNACE.excessAirFraction, nN2 = nO2 * (1 + ex) * 79 / 21, Tair = FURNACE.airTemperature_C + 273.15;
  const flue = (nCO2 * sensibleEnthalpy_J_per_mol('CO2', T_K) + nH2O * sensibleEnthalpy_J_per_mol('H2O', T_K)
    + nN2 * sensibleEnthalpy_J_per_mol('N2', T_K) + nO2 * ex * sensibleEnthalpy_J_per_mol('O2', T_K)) / 1000;
  const air = (nO2 * (1 + ex) * sensibleEnthalpy_J_per_mol('O2', Tair) + nN2 * sensibleEnthalpy_J_per_mol('N2', Tair)) / 1000;
  return flue - air;
}

/* ---------- 6. COLD BOX: Peng-Robinson equation of state ----------
   Components [H2, CH4, C2H4, C2H6, C3 (as propylene), C4+ (as 1-butene)]. ChemSep binary interaction parameters.
   Ideal-gas enthalpy: NASA polynomials (McBride, Gordon and Reno). */
const PR = {
  criticalTemperature_K: [33.145, 190.564, 282.350, 305.322, 364.211, 419.290],
  criticalPressure_Pa: [12.964e5, 45.992e5, 50.418e5, 48.722e5, 45.550e5, 40.051e5],
  acentricFactor: [-0.219, 0.01142, 0.0866, 0.0995, 0.146, 0.192],
  kij: [[0, -0.0044, 0.0633, -0.0781, -0.1037, 0], [-0.0044, 0, 0.0244, -0.0059, 0.033, 0],
        [0.0633, 0.0244, 0, 0.0078, 0, 0], [-0.0781, -0.0059, 0.0078, 0, 0.0089, 0],
        [-0.1037, 0.033, 0, 0.0089, 0, 0.0004], [0, 0, 0, 0, 0.0004, 0]],
  nasa: [[2.344331120e+00, 7.980520750e-03, -1.947815100e-05, 2.015720940e-08, -7.376117610e-12, -9.179351730e+02],
         [5.149876130e+00, -1.367097880e-02, 4.918005990e-05, -4.847430260e-08, 1.666939560e-11, -1.024664760e+04],
         [3.959201480e+00, -7.570522470e-03, 5.709902920e-05, -6.915887530e-08, 2.698843730e-11, 5.089775930e+03],
         [4.291424920e+00, -5.501542700e-03, 5.994382880e-05, -7.084662850e-08, 2.686857710e-11, -1.152220550e+04],
         [3.834645240e+00, 3.290784050e-03, 5.052281840e-05, -6.662514180e-08, 2.637075850e-11, 7.538382950e+02],
         [4.426740730e+00, 6.639462490e-03, 6.806528150e-05, -9.287535620e-08, 3.734739490e-11, -2.115327960e+03]]
};
function idealGasEnthalpy_J_per_mol(z, T) {
  let h = 0;
  for (let i = 0; i < 6; i++) { const a = PR.nasa[i]; h += z[i] * GAS_CONSTANT * T * (a[0] + a[1] * T / 2 + a[2] * T * T / 3 + a[3] * T * T * T / 4 + a[4] * T * T * T * T / 5 + a[5] / T); }
  return h;
}
function pureComponentParameters(T) {
  const a = [], b = [], da = [];
  for (let i = 0; i < 6; i++) {
    const Tc = PR.criticalTemperature_K[i], Pc = PR.criticalPressure_Pa[i], w = PR.acentricFactor[i];
    const m = 0.37464 + 1.54226 * w - 0.26992 * w * w, ac = 0.45724 * GAS_CONSTANT * GAS_CONSTANT * Tc * Tc / Pc;
    const alpha = 1 + m * (1 - Math.sqrt(T / Tc));
    a[i] = ac * alpha * alpha; b[i] = 0.07780 * GAS_CONSTANT * Tc / Pc; da[i] = -ac * m * alpha / Math.sqrt(T * Tc);
  }
  return { a, b, da };
}
function cubicRoots(c2, c1, c0) {          // real roots of Z^3 + c2 Z^2 + c1 Z + c0 = 0
  const q = (3 * c1 - c2 * c2) / 9, r = (9 * c2 * c1 - 27 * c0 - 2 * c2 * c2 * c2) / 54, d = q * q * q + r * r, s = -c2 / 3;
  if (d > 0) { const sq = Math.sqrt(d); return [s + Math.cbrt(r + sq) + Math.cbrt(r - sq)]; }
  const th = Math.acos(Math.max(-1, Math.min(1, r / Math.sqrt(-q * q * q)))), rt = 2 * Math.sqrt(-q);
  return [rt * Math.cos(th / 3) + s, rt * Math.cos((th + 2 * Math.PI) / 3) + s, rt * Math.cos((th + 4 * Math.PI) / 3) + s];
}
/* One phase: compressibility Z, ln(fugacity coefficients) and departure enthalpy (J/mol). */
function phaseProperties(z, T, P, liquid, pp) {
  const { a, b, da } = pp; let am = 0, bm = 0, dam = 0; const ai = new Array(6).fill(0);
  for (let i = 0; i < 6; i++) { bm += z[i] * b[i];
    for (let j = 0; j < 6; j++) { const s = Math.sqrt(a[i] * a[j]), k = 1 - PR.kij[i][j], aij = s * k;
      ai[i] += z[j] * aij; am += z[i] * z[j] * aij; dam += z[i] * z[j] * k * (da[i] * a[j] + a[i] * da[j]) / (2 * s); } }
  const A = am * P / (GAS_CONSTANT * GAS_CONSTANT * T * T), B = bm * P / (GAS_CONSTANT * T), SQ2 = Math.SQRT2;
  const roots = cubicRoots(-(1 - B), A - 3 * B * B - 2 * B, -(A * B - B * B - B * B * B)).filter(v => v > B);
  const Z = liquid ? Math.min(...roots) : Math.max(...roots);
  const L = Math.log((Z + (1 + SQ2) * B) / (Z + (1 - SQ2) * B));
  const lnphi = [];
  for (let i = 0; i < 6; i++) lnphi[i] = b[i] / bm * (Z - 1) - Math.log(Z - B) - A / (2 * SQ2 * B) * (2 * ai[i] / am - b[i] / bm) * L;
  return { Z, lnphi, departureEnthalpy: GAS_CONSTANT * T * (Z - 1) + (T * dam - am) / (2 * SQ2 * bm) * L };
}
/* Isothermal flash at T, P. Michelsen tangent-plane stability test from Wilson K values; an unstable feed
   is flashed by Rachford-Rice with successive substitution of K = phi_L/phi_V. Returns vapor fraction V,
   liquid x, vapor y and molar enthalpy h (J/mol). */
function flashTP(z, T, P) {
  const pp = pureComponentParameters(T);
  const L0 = phaseProperties(z, T, P, true, pp), G0 = phaseProperties(z, T, P, false, pp);
  const gibbs = ph => z.reduce((s, zi, i) => s + (zi > 0 ? zi * (Math.log(zi) + ph.lnphi[i]) : 0), 0);
  const feedLiquid = Math.abs(L0.Z - G0.Z) > 1e-9 ? gibbs(L0) < gibbs(G0) : L0.Z < 0.3;
  const lnphiFeed = (feedLiquid ? L0 : G0).lnphi;
  const Kw = PR.criticalTemperature_K.map((Tc, i) => PR.criticalPressure_Pa[i] / P * Math.exp(5.373 * (1 + PR.acentricFactor[i]) * (1 - Tc / T)));
  const trialPhase = (w, vapor) => {
    let S = 1;
    for (let it = 0; it < 200; it++) {
      const sw = w.reduce((s, v) => s + v, 0), wn = w.map(v => v / sw);
      const ph = phaseProperties(wn, T, P, !vapor, pp);
      const W = z.map((zi, i) => zi * Math.exp(lnphiFeed[i] - ph.lnphi[i]));
      S = W.reduce((s, v) => s + v, 0);
      const d = W.reduce((m, Wi, i) => z[i] > 0 ? Math.max(m, Math.abs(Math.log(Wi / w[i]))) : m, 0);
      w = W; if (d < 1e-8) break;
    }
    const wn = w.map(v => v / S), trivial = wn.every((v, i) => Math.abs(v - z[i]) < 1e-6);
    return { w: wn, S, unstable: !trivial && S > 1 + 1e-8 };
  };
  const tv = trialPhase(z.map((zi, i) => zi * Kw[i]), true), tl = trialPhase(z.map((zi, i) => zi / Kw[i]), false);
  const single = () => feedLiquid ? { V: 0, x: z, y: z, h: idealGasEnthalpy_J_per_mol(z, T) + L0.departureEnthalpy }
                                  : { V: 1, x: z, y: z, h: idealGasEnthalpy_J_per_mol(z, T) + G0.departureEnthalpy };
  if (!tv.unstable && !tl.unstable) return single();
  let K = tv.unstable && (!tl.unstable || tv.S >= tl.S) ? tv.w.map((w, i) => z[i] > 0 ? w / z[i] : 1) : tl.w.map((w, i) => z[i] > 0 ? z[i] / w : 1);
  let V = 0.5, x = z, y = z, best = null;
  for (let it = 0; it < 500; it++) {
    if (!K.every(Number.isFinite)) K = Kw.slice();
    const Kp = K.filter((k, i) => z[i] > 0), Kmax = Math.max(...Kp), Kmin = Math.min(...Kp);
    if (Kmax <= 1 || Kmin >= 1) return single();
    const g = v => z.reduce((s, zi, i) => s + zi * (K[i] - 1) / (1 + v * (K[i] - 1)), 0);
    let lo = 1 / (1 - Kmax) + 1e-9, hi = 1 / (1 - Kmin) - 1e-9;
    for (let k = 0; k < 80; k++) { V = (lo + hi) / 2; if (g(V) > 0) lo = V; else hi = V; }
    x = z.map((zi, i) => zi / (1 + V * (K[i] - 1))); const sx = x.reduce((s, v) => s + v, 0); x = x.map(v => v / sx);
    y = x.map((xi, i) => K[i] * xi); const sy = y.reduce((s, v) => s + v, 0); y = y.map(v => v / sy);
    const L = phaseProperties(x, T, P, true, pp), G = phaseProperties(y, T, P, false, pp);
    let err = 0; const Kn = [], damp = it < 100 ? 1 : 0.5;
    for (let i = 0; i < 6; i++) { if (z[i] <= 0) { Kn[i] = 1; continue; } const kn = Math.exp(L.lnphi[i] - G.lnphi[i]); err += Math.abs(Math.log(kn / K[i]));
      Kn[i] = Math.exp(damp * Math.log(kn) + (1 - damp) * Math.log(K[i])); }
    K = Kn;
    const sol = V <= 0 || V >= 1 ? single() : { V, x, y, h: V * (idealGasEnthalpy_J_per_mol(y, T) + G.departureEnthalpy) + (1 - V) * (idealGasEnthalpy_J_per_mol(x, T) + L.departureEnthalpy) };
    if (err < 1e-8) return sol;
    if (!best || err < best.err) best = { err, sol };
  }
  if (best && best.err < 1e-6) return best.sol;
  throw new Error('FAILED: cold-box flash did not converge at ' + T.toFixed(1) + ' K');
}
/* Cold box. z: feed mol fractions [H2, CH4, C2H4, C2H6, C3, C4]; n: feed mol per kg ethylene.
   Cold-end temperature: the temperature at which one equilibrium stage leaves (1 - recovery) of the ethylene
   in the fuel-gas vapor. Refrigeration duty per level: feed enthalpy drop between the level limits, less the
   enthalpy that the fuel gas and the condensate take up while they rewarm against the feed with a 5 K approach,
   in steps of at most 10 K, never below zero in a step. Returns cold end (K) and duties (kJ/kg ethylene)
   at the propylene, ethylene and methane levels. */
function coldBox(z, n) {
  const P = DESIGN.coldBoxPressure_Pa, approach = DESIGN.coldBoxApproach_K;
  const recoveryAt = T => { const f = flashTP(z, T, P); return 1 - f.V * f.y[2] / z[2]; };
  let lo = 110, hi = 273.15, Tc;
  if (recoveryAt(hi) >= DESIGN.ethyleneRecovery) Tc = hi;
  else { for (let k = 0; k < 30; k++) { Tc = (lo + hi) / 2; if (recoveryAt(Tc) < DESIGN.ethyleneRecovery) hi = Tc; else lo = Tc; } Tc = (lo + hi) / 2; }
  const end = flashTP(z, Tc, P), nFuelGas = end.V * n, nCondensate = (1 - end.V) * n;
  const feedH = T => flashTP(z, T, P).h * n / 1000;
  const vaporH = (c, T) => idealGasEnthalpy_J_per_mol(c, T) + phaseProperties(c, T, P, false, pureComponentParameters(T)).departureEnthalpy;
  const returnH = (c, mol, T, Tmax, vapor) => mol > 0 ? (vapor ? vaporH(c, Math.min(Tmax, Math.max(Tc, T))) : flashTP(c, Math.min(Tmax, Math.max(Tc, T)), P).h) * mol / 1000 : 0;
  const Tb = [DESIGN.coldBoxFeedTemperature_K, Math.max(DESIGN.refrigerationLevelLimits_K[0], Tc), Math.max(DESIGN.refrigerationLevelLimits_K[1], Tc), Tc];
  const duty = [];
  for (let k = 0; k < 3; k++) {
    duty[k] = 0;
    if (Tb[k] <= Tb[k + 1]) continue;
    const steps = Math.ceil((Tb[k] - Tb[k + 1]) / 10), dT = (Tb[k] - Tb[k + 1]) / steps;
    let Th = Tb[k], Hh = feedH(Th), Gh = returnH(end.y, nFuelGas, Th - approach, DESIGN.fuelGasReturnTemperature_K, true), Lh = returnH(end.x, nCondensate, Th - approach, DESIGN.condensateReturnTemperature_K, false);
    for (let m = 1; m <= steps; m++) {
      const Tl = Tb[k] - m * dT, Hl = feedH(Tl), Gl = returnH(end.y, nFuelGas, Tl - approach, DESIGN.fuelGasReturnTemperature_K, true), Ll = returnH(end.x, nCondensate, Tl - approach, DESIGN.condensateReturnTemperature_K, false);
      duty[k] += Math.max(0, (Hh - Hl) - (Gh - Gl) - (Lh - Ll));
      Hh = Hl; Gh = Gl; Lh = Ll;
    }
  }
  return { coldEnd_K: Tc, duty_kJ_per_kg: duty };
}
/* Refrigeration work of the cascade: each condenser load (duty + work) goes to the next warmer cycle. */
function cascadeWork_kJ_per_kg(duty) {
  const wMethane = duty[2] / DESIGN.copMethane;
  const wEthylene = (duty[1] + duty[2] + wMethane) / DESIGN.copEthylene;
  const wPropylene = (duty[0] + duty[1] + duty[2] + wMethane + wEthylene) / DESIGN.copPropylene;
  return wMethane + wEthylene + wPropylene;
}

/* ---------- 7. COLUMNS: Fenske-Underwood-Gilliland shortcut ----------
   Keys recovered 99.5 %, reflux R = 1.2 R_min, saturated-liquid feed (q = 1).
   Fenske:   N_min = ln[(d_LK/b_LK)(b_HK/d_HK)] / ln(alpha_LK)
   Underwood: sum_i alpha_i z_i/(alpha_i - theta) = 0 ;  R_min + 1 = sum_i alpha_i x_D,i/(alpha_i - theta)
   Gilliland (Eduljee): Y = 0.75 (1 - X^0.5668), X = (R - R_min)/(R + 1), N = (N_min + Y)/(1 - Y)
   Condenser duty = (R + 1) D lambda_top ; reboiler duty = condenser duty + bottoms sensible heat (top -> bottom).
   Relative volatilities to the heavy key, latent heats and densities: Peng-Robinson at the reference
   composition and the column pressure (thermo 0.6.1, ChemSep kij). */
const COLUMN = {
  keyRecovery: 0.995, refluxFactor: 1.2, trayEfficiency: 0.70, traySpacing_m: 0.6, designHours_per_y: 8000,
  liquidHeatCapacity_kJ_per_kgK: 2.4,
  lpSteamTemperature_C: 148, coolingWaterIn_C: 30, coolingWaterOut_C: 35,
  condenserU_W_per_m2K: 700, reboilerU_W_per_m2K: 1000,      // Towler and Sinnott 2022 Table 19.1
  cepciEscalation: 607.5 / 532.9,                            // Jan 2010 USGC -> 2019
  allowableStress_MPa: 88.9, jointEfficiency: 0.85, corrosionAllowance_m: 0.002,   // A285 plate, ASME VIII Div. 1
  // Column cost on the reference-plant basis: Towler sizing of the reference C2 splitter and deethanizer is
  // 3.84 times the 25.36 MUSD fractionation share of the reference plant.
  costBasisFactor: 0.2607, deethanizerReferenceInstalledCost_MUSD: 24.535,
  deethanizer: { pressure_bar: 25, lightKey: 'c2h6', heavyKey: 'c3', alpha: { c2h4: 2.660, c2h6: 2.044, c3: 1, c4: 0.424 },
    molarMass: { c2h4: 28.05, c2h6: 30.07, c3: 42.08, c4: 54.09 }, latentTop_J_per_mol: 8690, vaporDensity_kg_m3: 49.1, liquidDensity_kg_m3: 407,
    topTemperature_C: -7.7, bottomTemperature_C: 96.2, condenserCOP: 3.494 },
  depropanizer: { pressure_bar: 16, lightKey: 'c3', heavyKey: 'c4', alpha: { c3: 2.337, c4: 1 }, molarMass: { c3: 42.08, c4: 54.09 },
    latentTop_J_per_mol: 12950, vaporDensity_kg_m3: 34.6, liquidDensity_kg_m3: 487, topTemperature_C: 38.6, bottomTemperature_C: 95.5, condenserCOP: null },
  debutanizer: { pressure_bar: 5, lightKey: 'c4', heavyKey: 'c5', alpha: { c4: 3.095, c5: 1 }, molarMass: { c4: 54.09, c5: 72.1 },
    latentTop_J_per_mol: 19750, vaporDensity_kg_m3: 11.5, liquidDensity_kg_m3: 603, topTemperature_C: 45.1, bottomTemperature_C: 114.9, condenserCOP: null },
  quenchCondensationHeat_kJ_per_kg: 400      // C5+ condensed in the quench tower and the compressor interstage coolers
};
function shortcutColumn(c, feed_mol_per_kg) {
  const keys = Object.keys(c.alpha), a = c.alpha, f = {};
  keys.forEach(k => f[k] = Math.max(feed_mol_per_kg[k] || 0, 1e-12));
  const F = keys.reduce((s, k) => s + f[k], 0), aLK = a[c.lightKey], rec = COLUMN.keyRecovery;
  const top = {}; keys.forEach(k => top[k] = a[k] > aLK ? f[k] : 0);       // lighter than the light key: all to the top
  top[c.lightKey] = rec * f[c.lightKey]; top[c.heavyKey] = (1 - rec) * f[c.heavyKey];
  const D = keys.reduce((s, k) => s + top[k], 0);
  const Nmin = Math.log((rec / (1 - rec)) * (rec / (1 - rec))) / Math.log(aLK);
  const underwood = th => keys.reduce((s, k) => s + a[k] * f[k] / F / (a[k] - th), 0);
  let lo = 1 + 1e-9, hi = aLK - 1e-9;
  for (let i = 0; i < 100; i++) { const m = (lo + hi) / 2; if (underwood(m) > 0) hi = m; else lo = m; }
  const theta = (lo + hi) / 2;
  const Rmin = Math.max(0.05, keys.reduce((s, k) => s + a[k] * top[k] / D / (a[k] - theta), 0) - 1);
  const R = COLUMN.refluxFactor * Rmin, Xg = (R - Rmin) / (R + 1), Yg = 0.75 * (1 - Math.pow(Xg, 0.5668));
  const N = (Nmin + Yg) / (1 - Yg), vapor = (R + 1) * D;
  const topMolarMass = keys.reduce((s, k) => s + top[k] * c.molarMass[k], 0) / D;
  const bottoms_kg = keys.reduce((s, k) => s + (f[k] - top[k]) * c.molarMass[k], 0) / 1000;
  const condenser = vapor * c.latentTop_J_per_mol / 1000;
  return { refluxRatio: R, minimumRefluxRatio: Rmin, theoreticalStages: N, vapor_mol_per_kg: vapor, topMolarMass, bottoms_kg_per_kg: bottoms_kg,
    condenserDuty_kJ_per_kg: condenser,
    reboilerDuty_kJ_per_kg: condenser + bottoms_kg * COLUMN.liquidHeatCapacity_kJ_per_kgK * (c.bottomTemperature_C - c.topTemperature_C) };
}
/* Installed cost (MUSD, Towler and Sinnott 2022 basis) from column size.
   Diameter: u_v = (-0.171 l_t^2 + 0.27 l_t - 0.047) sqrt((rho_L - rho_V)/rho_V) (Eq. 17.47), D = sqrt(4 V/(pi rho_V u_v)).
   Shell thickness: t = P D/(2 S E - 1.2 P) + corrosion allowance (ASME, Eq. 14.13).
   Purchased cost Table 7.2; installed with Hand factors (column 4, exchanger 3.5). */
function columnInstalledCost_MUSD(c, s, capacity_kt_per_y) {
  const rate_kg_s = capacity_kt_per_y * 1e6 / (COLUMN.designHours_per_y * 3600);
  const vaporMass_kg_s = s.vapor_mol_per_kg * s.topMolarMass / 1000 * rate_kg_s;
  const lt = COLUMN.traySpacing_m, uv = (-0.171 * lt * lt + 0.27 * lt - 0.047) * Math.sqrt((c.liquidDensity_kg_m3 - c.vaporDensity_kg_m3) / c.vaporDensity_kg_m3);
  const Dc = Math.max(0.5, Math.sqrt(4 * vaporMass_kg_s / (Math.PI * c.vaporDensity_kg_m3 * uv)));
  const trays = Math.ceil(s.theoreticalStages / COLUMN.trayEfficiency), H = trays * lt + 4;
  const Pd = 1.1 * c.pressure_bar * 0.1;
  const t = Pd * Dc / (2 * COLUMN.allowableStress_MPa * COLUMN.jointEfficiency - 1.2 * Pd) + COLUMN.corrosionAllowance_m;
  const shellMass = Math.PI * Dc * (H + 0.8 * Dc) * t * 7850;
  const shell = (11600 + 34 * Math.pow(Math.min(Math.max(shellMass, 160), 250000), 0.85)) * Math.max(1, Math.ceil(shellMass / 250000));
  const trayCost = trays * (130 + 440 * Math.pow(Math.min(Math.max(Dc, 0.5), 5), 1.8));
  const condenser_kW = s.condenserDuty_kJ_per_kg * rate_kg_s, reboiler_kW = s.reboilerDuty_kJ_per_kg * rate_kg_s;
  const lmtd = (d1, d2) => Math.abs(d1 - d2) < 1e-6 ? d1 : (d1 - d2) / Math.log(d1 / d2);
  const dTc = c.condenserCOP ? 5 : lmtd(c.topTemperature_C - COLUMN.coolingWaterIn_C, c.topTemperature_C - COLUMN.coolingWaterOut_C);
  const areaC = condenser_kW * 1000 / (COLUMN.condenserU_W_per_m2K * dTc), areaR = reboiler_kW * 1000 / (COLUMN.reboilerU_W_per_m2K * (COLUMN.lpSteamTemperature_C - c.bottomTemperature_C));
  const exchanger = (A, Amin, Amax, a, b, nexp) => { const k = Math.max(1, Math.ceil(A / Amax)); return k * (a + b * Math.pow(Math.max(A / k, Amin), nexp)); };
  const cond = exchanger(areaC, 10, 1000, 28000, 54, 1.2), reb = exchanger(areaR, 10, 500, 29000, 400, 0.9);
  return { diameter_m: Dc, height_m: H, trays, installed_MUSD: COLUMN.cepciEscalation * (4 * (shell + trayCost) + 3.5 * (cond + reb)) / 1e6 };
}

/* ---------- 8. CAPITAL ----------
   Total bare-module cost (TBMC) of the reference plant: 126.8 MUSD at 610 kt/y (Mittal et al. 2025 SI).
   Section shares: furnace 0.30, compression 0.25, cold box 0.25, fractionation 0.20 (assumption on the same source).
   Each section scales with its own load: TBMC = 126.8 (cap/610)^0.65 * sum_s share_s (load_s/load_s,ref)^e_s.
   Total capital investment TCI = 2.5 TBMC. Annual charge = 0.10 TCI; O&M = 0.075 TCI + labor. */
const CAPITAL = {
  referenceTBMC_MUSD: 126.8, referenceCapacity_kt_per_y: 610, capacityExponent: 0.65,
  shareFurnace: 0.30, shareCompression: 0.25, shareColdBox: 0.25, shareFractionation: 0.20,
  referenceCompressorWork_kJ_per_kg: 1134, compressorExponent: 0.70,
  referenceColdBoxWork_kJ_per_kg: 1274.9, coldBoxExponent: 0.70,      // cold-box work of the reference case (850 degC, 0.35 s)
  referenceC2SplitterLoad: 195, fractionationExponent: 0.60,          // reflux ratio x stages of the reference plant
  furnaceExponent: 0.65, tciPerTBMC: 2.5, omFractionOfTCI: 0.075
};

/* ---------- PLANT CALCULATION ---------- */
function calculatePlant(inputs) {
  const p = inputs, warnings = [];
  const fired = p.heatSource === 'fired';

  /* 1. Reaction */
  let reaction, gpSD = null, outsideTrainingRange = [];
  if (directComposition) reaction = directComposition;
  else {
    if (!gpParameters) throw new Error(gpStatus.message);
    const g = predictReaction(p); reaction = g.mean; gpSD = g.sd; outsideTrainingRange = g.outsideTrainingRange;
    if (outsideTrainingRange.length) warnings.push('WARNING outside GP training range (' + outsideTrainingRange.join(', ') + '): extrapolated; see GP SD');
  }
  const conversion = reaction.x_c2h6;
  const yEthylene = reaction.y_c2h4_kg_per_kg_ethane, yAcetylene = reaction.y_c2h2_kg_per_kg_ethane || 0;
  const yEthane = reaction.y_c2h6_kg_per_kg_ethane || Math.max(0, 1 - conversion), yHydrogenRaw = reaction.y_h2_kg_per_kg_ethane || 0;

  /* 2. Acetylene hydrogenation and product basis.
     C2H2 + H2 -> C2H4 (90 %) and C2H2 + 2 H2 -> C2H6 (10 %), to 5 mol ppm C2H2 in the ethylene product.
     Final ethylene yield Y_E,final = Y_E + made ethylene; coil ethane m_coil = 1/(r_E Y_E,final);
     fresh ethane = (X - made ethane) m_coil; recycle = m_coil - fresh. */
  const nAcetylene = yAcetylene * 1000 / MOLAR_MASS.acetylene, nEthylene = yEthylene * 1000 / MOLAR_MASS.ethylene, nEthane = yEthane * 1000 / MOLAR_MASS.ethane;
  const ppm = DESIGN.acetyleneTarget_ppm * 1e-6, r = DESIGN.ethyleneRecovery, sel = DESIGN.acetyleneToEthyleneSelectivity;
  const nAcetyleneLeft = Math.min(nAcetylene, ppm * r * (nEthylene + sel * nAcetylene) / (1 + ppm * r * sel));
  const nAcetyleneReacted = Math.max(0, nAcetylene - nAcetyleneLeft);
  const nEthyleneMade = nAcetyleneReacted * sel, nEthaneMade = nAcetyleneReacted * (1 - sel);
  const hydrogenNeed_kg = nAcetyleneReacted * (sel + 2 * (1 - sel)) * MOLAR_MASS.hydrogen / 1000;
  const ethyleneMade_kg = nEthyleneMade * MOLAR_MASS.ethylene / 1000, ethaneMade_kg = nEthaneMade * MOLAR_MASS.ethane / 1000;
  const coilEthane = 1 / Math.max(r * (yEthylene + ethyleneMade_kg), 1e-12);
  const freshEthane = Math.max(0, (conversion - ethaneMade_kg) * coilEthane);
  const recycleEthane = Math.max(0, coilEthane - freshEthane);
  const dilutionSteam = coilEthane * p.steamToEthane_kg_per_kg;
  const hydrogenFromPlant = Math.min(yHydrogenRaw, hydrogenNeed_kg), hydrogenExternal = Math.max(0, hydrogenNeed_kg - yHydrogenRaw);
  const product = {        // kg per kg ethylene product
    methane: (reaction.y_ch4_kg_per_kg_ethane || 0) * coilEthane,
    hydrogen: Math.max(0, yHydrogenRaw - hydrogenFromPlant) * coilEthane,
    acetyleneLeft: nAcetyleneLeft * MOLAR_MASS.acetylene / 1000 * coilEthane,
    c3: (reaction.y_c3_kg_per_kg_ethane || 0) * coilEthane,
    c4plus: (reaction.y_c4plus_kg_per_kg_ethane || 0) * coilEthane
  };
  const c4PlusCoil = reaction.y_c4plus_kg_per_kg_ethane || 0;
  product.c5plus = Number.isFinite(reaction.y_c5plus_kg_per_kg_ethane) ? Math.min(reaction.y_c5plus_kg_per_kg_ethane, c4PlusCoil) * coilEthane : c5PlusShare(c4PlusCoil) * product.c4plus;
  if (!Number.isFinite(reaction.y_c5plus_kg_per_kg_ethane) && c4PlusCoil > 0 && c4PlusCoil < 0.0092) warnings.push('WARNING C5+ share below the Cantera fit range; share taken toward zero');
  const raw = { ethylene: yEthylene * coilEthane, ethane: Math.max(0, recycleEthane - ethaneMade_kg * coilEthane), hydrogen: yHydrogenRaw * coilEthane, acetylene: yAcetylene * coilEthane };
  const nC2Total = Math.max(1e-12, nAcetylene + nEthylene + nEthane);
  const acetyleneConverter = { enabled: true, targetPpm: DESIGN.acetyleneTarget_ppm, selectivity: sel,
    rawKg: raw.acetylene, convertedKg: nAcetyleneReacted * MOLAR_MASS.acetylene / 1000 * coilEthane, residualKg: product.acetyleneLeft,
    residualPpm: nAcetyleneLeft / Math.max(1e-12, nAcetyleneLeft + r * (nEthylene + nEthyleneMade)) * 1e6,
    rawC2MolPct: 100 * nAcetylene / nC2Total, conversion: nAcetylene > 0 ? nAcetyleneReacted / nAcetylene : 0,
    beds: nAcetylene / nC2Total < 0.005 ? 1 : (nAcetylene / nC2Total <= 0.017 ? 2 : 3),
    rawEthyleneKg: raw.ethylene, rawEthaneKg: raw.ethane, rawH2Kg: raw.hydrogen,
    ethyleneRecoveredKg: ethyleneMade_kg * coilEthane, ethaneMadeKg: ethaneMade_kg * coilEthane,
    h2ConsumedKg: hydrogenNeed_kg * coilEthane, h2FromPlantKg: hydrogenFromPlant * coilEthane, h2ExternalKg: hydrogenExternal * coilEthane };
  if (acetyleneConverter.h2ExternalKg > 1e-9) warnings.push('WARNING acetylene converter needs external H2; its cost is not included');
  const ethyleneToFuelGas = 1 / r - 1;          // kg per kg product lost to the fuel gas in the cold box

  /* 3. Heat supply.
     Reactor duty Q = feed preheat (150 -> 650 degC, sensible) + radiant duty (650 degC -> COT and cracking, GP). */
  const cpFeed = coilEthane * DESIGN.ethaneHeatCapacity_kJ_per_kgK + dilutionSteam * DESIGN.steamHeatCapacity_kJ_per_kgK;   // kJ/K per kg ethylene
  const feedPreheatDuty = cpFeed * (DESIGN.coilInletTemperature_C - DESIGN.feedPreheatStart_C);
  const radiantDuty = reaction.heat_MJ_per_kg_ethane * coilEthane * 1000;
  const reactorDuty = feedPreheatDuty + radiantDuty;                                                    // kJ/kg ethylene
  const effluentSensibleHeat = cpFeed * (p.coilOutletTemperature_C - DESIGN.feedPreheatStart_C);
  const tleSteam = DESIGN.tleRecoveryFraction * effluentSensibleHeat;
  const fuelGas = (product.methane * DESIGN.methaneLHV_MJ_per_kg + product.hydrogen * DESIGN.hydrogenLHV_MJ_per_kg + ethyleneToFuelGas * DESIGN.ethyleneLHV_MJ_per_kg) * 1000;
  let purchasedHeat, furnace = null, convectionSteam = 0;
  if (fired && p.firedHeatModel === 'radiant') {
    let fuel = reactorDuty / 0.6, etaRadiant = 0.45, etaOverall = 0.92;
    for (let it = 0; it < 3; it++) {
      const burned = Math.min(fuelGas, fuel), ng = fuel - burned;
      const frac = { ch4: (burned > 0 ? product.methane * DESIGN.methaneLHV_MJ_per_kg * 1000 / fuelGas * burned : 0) + ng,
        h2: burned > 0 ? product.hydrogen * DESIGN.hydrogenLHV_MJ_per_kg * 1000 / fuelGas * burned : 0,
        c2h4: burned > 0 ? ethyleneToFuelGas * DESIGN.ethyleneLHV_MJ_per_kg * 1000 / fuelGas * burned : 0 };
      const total = frac.ch4 + frac.h2 + frac.c2h4; for (const s in frac) frac[s] /= total;
      etaRadiant = 1 - flueGasEnthalpyPerFuelLHV(frac, FURNACE.bridgewallTemperature_C + 273.15);
      etaOverall = 1 - flueGasEnthalpyPerFuelLHV(frac, FURNACE.stackTemperature_C + 273.15) - FURNACE.casingLossFraction;
      fuel = Math.max(radiantDuty / etaRadiant, (radiantDuty + feedPreheatDuty) / etaOverall);
    }
    convectionSteam = Math.max(0, fuel * (etaOverall - etaRadiant) - feedPreheatDuty);
    purchasedHeat = fuel;
    furnace = { radiantEfficiency: etaRadiant, overallEfficiency: etaOverall, equivalentFixedEfficiency: reactorDuty / fuel,
      fuelLHV_kJ_per_kg: fuel, convectionDuty_kJ_per_kg: fuel * (etaOverall - etaRadiant), convectionSteam_kJ_per_kg: convectionSteam };
  } else {
    purchasedHeat = reactorDuty / ((fired ? p.firedEfficiencyFixed_percent : p.electricEfficiency_percent) / 100);
  }
  const fuelGasBurned = fired ? Math.min(fuelGas, purchasedHeat) : 0;
  const fuelGasSurplus = fuelGas - fuelGasBurned, fuelGasSold = p.fuelGasUse === 'sell' ? fuelGasSurplus : 0;
  const naturalGasBought = fired ? Math.max(0, purchasedHeat - fuelGas) : 0;
  const electricHeat = fired ? 0 : purchasedHeat;

  /* 4. Coil heat flux and tube metal temperature.
     Coil volume = mean volumetric flow x residence time; inside area = 4 V/d; mean flux q = radiant duty/area. */
  const rate_kg_s = p.plantCapacity_kt_per_y * 1e6 / (COLUMN.designHours_per_y * 3600);
  const coilMol = coilEthane * 1000 / MOLAR_MASS.ethane * (1 + conversion / 2) + dilutionSteam * 1000 / MOLAR_MASS.water;
  const coilVolume = coilMol * rate_kg_s * GAS_CONSTANT * ((DESIGN.coilInletTemperature_C + p.coilOutletTemperature_C) / 2 + 273.15) / (p.coilPressure_bar * 1e5) * p.residenceTime_s;
  const coilArea = 4 * coilVolume / FURNACE.coilInsideDiameter_m, radiant_kW = radiantDuty * rate_kg_s, meanFlux = radiant_kW / coilArea;
  const tmt = p.coilOutletTemperature_C + FURNACE.peakFluxFactor * meanFlux * 1000 / FURNACE.filmConductance_W_per_m2K;
  const coilCount = coilVolume / FURNACE.coilVolumePerCoil_m3;
  let coilAreaUsed = coilArea, tmtStatus = 'OK';
  if (fired && tmt > FURNACE.tubeMetalLimit_C) {
    const margin = FURNACE.tubeMetalLimit_C - p.coilOutletTemperature_C;
    if (margin <= 20) { tmtStatus = 'FAILED'; coilAreaUsed = coilArea * 50; warnings.push('FAILED tube metal temperature: COT within 20 K of the alloy limit'); }
    else { tmtStatus = 'WARNING'; coilAreaUsed = FURNACE.peakFluxFactor * radiant_kW * 1000 / (FURNACE.filmConductance_W_per_m2K * margin);
      warnings.push('WARNING tube metal temperature: coil area increased ' + (coilAreaUsed / coilArea).toFixed(2) + ' times to keep ' + FURNACE.tubeMetalLimit_C + ' degC'); }
  }
  const coilHeat = { coilVolume_m3: coilVolume, coilArea_m2: coilArea, coilAreaUsed_m2: coilAreaUsed, meanFlux_kW_m2: meanFlux,
    tubeMetalTemperatureMaxC: tmt, tmtStatus, coilCount, dutyPerCoil_kW: radiant_kW / coilCount,
    radiantDuty_kJ_per_kg: radiantDuty, feedPreheatDuty_kJ_per_kg: feedPreheatDuty };

  /* 5. Compression: W = N gamma/(gamma-1) R T1 [r^((gamma-1)/gamma) - 1]/eta_is per mol, r = (P2/P1)^(1/N).
     The compressor takes the full reactor effluent (dry), before acetylene hydrogenation. */
  const nGas = raw.ethylene * 1000 / MOLAR_MASS.ethylene + raw.ethane * 1000 / MOLAR_MASS.ethane + product.methane * 1000 / MOLAR_MASS.methane
    + raw.hydrogen * 1000 / MOLAR_MASS.hydrogen + raw.acetylene * 1000 / MOLAR_MASS.acetylene + product.c3 * 1000 / MOLAR_MASS.c3 + product.c4plus * 1000 / MOLAR_MASS.c4;
  const g = DESIGN.compressorHeatCapacityRatio, N = DESIGN.compressorStages, stageRatio = Math.pow(DESIGN.compressorDischarge_bar / DESIGN.compressorSuction_bar, 1 / N);
  const compressorWork = N * (g / (g - 1)) * 8.314 * DESIGN.compressorSuctionTemperature_K * (Math.pow(stageRatio, (g - 1) / g) - 1) / DESIGN.compressorIsentropicEfficiency * nGas / 1000;

  /* 6. Cold box: feed after hydrogenation, without the C5+ that left in the quench. */
  const c4Only = Math.max(0, product.c4plus - product.c5plus);
  const mol = { ethylene: (1 / r) * 1000 / MOLAR_MASS.ethylene, ethane: recycleEthane * 1000 / MOLAR_MASS.ethane, methane: product.methane * 1000 / MOLAR_MASS.methane,
    hydrogen: product.hydrogen * 1000 / MOLAR_MASS.hydrogen, acetylene: product.acetyleneLeft * 1000 / MOLAR_MASS.acetylene,
    c3: product.c3 * 1000 / MOLAR_MASS.c3, c4: c4Only * 1000 / MOLAR_MASS.c4 };
  const nColdBox = mol.ethylene + mol.ethane + mol.methane + mol.hydrogen + mol.acetylene + mol.c3 + mol.c4;
  const cb = coldBox([mol.hydrogen, mol.methane, mol.ethylene + mol.acetylene, mol.ethane, mol.c3, mol.c4].map(v => v / nColdBox), nColdBox);
  const refrigerationWork = cascadeWork_kJ_per_kg(cb.duty_kJ_per_kg);
  if (cb.coldEnd_K >= 273.15) warnings.push('WARNING cold box meets the recovery without refrigeration below 0 degC');

  /* 7a. C2 splitter. alpha = 1.85 - 0.018 P (P = 32 bar); N = 2.1 N_min; Underwood binary R_min with feed
     ethylene fraction z_F (capped at 0.995); R = max(1.15 R_min, (R_min + 0.9(1 - sqrt(X)))1.05);
     condenser duty (R + 1) x 280 kJ/kg ethylene on the propylene cycle. */
  const alpha = 1.85 - 0.018 * DESIGN.compressorDischarge_bar;
  const Nmin = Math.log((DESIGN.ethylenePurity / (1 - DESIGN.ethylenePurity)) * (0.99 / 0.01)) / Math.log(alpha);
  const Nact = Math.round(2.1 * Nmin);
  const ethyleneRecovered = mol.ethylene * r;
  const zF = Math.min(0.995, ethyleneRecovered / (ethyleneRecovered + mol.ethane));
  const Rmin = Math.max(0.5, (1 / (alpha - 1)) * (DESIGN.ethylenePurity / zF - alpha * (1 - DESIGN.ethylenePurity) / (1 - zF)));
  const gx = (Nact - Nmin) / (Nact + 1);
  const splitterReflux = Math.max(Rmin * 1.15, (Rmin + (1 - Math.sqrt(gx)) * 0.9) * 1.05);
  const splitterWork = (splitterReflux + 1) * DESIGN.c2SplitterLatentHeat_kJ_per_kg / DESIGN.copC2SplitterCondenser;

  /* 7b. Deethanizer (cold-box liquid C2 + C3 + C4), depropanizer (C3 + C4), debutanizer (C4 + quench C5+). */
  const deethanizer = shortcutColumn(COLUMN.deethanizer, { c2h4: ethyleneRecovered, c2h6: mol.ethane, c3: mol.c3, c4: c4Only * 1000 / 54.09 });
  const depropanizer = shortcutColumn(COLUMN.depropanizer, { c3: mol.c3, c4: c4Only * 1000 / 54.09 });
  const debutanizer = shortcutColumn(COLUMN.debutanizer, { c4: c4Only * 1000 / 54.09, c5: product.c5plus * 1000 / 72.1 });
  const deethanizerWork = deethanizer.condenserDuty_kJ_per_kg / COLUMN.deethanizer.condenserCOP;
  const coolingWater = depropanizer.condenserDuty_kJ_per_kg + debutanizer.condenserDuty_kJ_per_kg + product.c5plus * COLUMN.quenchCondensationHeat_kJ_per_kg;
  const reboilerSteam = deethanizer.reboilerDuty_kJ_per_kg + depropanizer.reboilerDuty_kJ_per_kg + debutanizer.reboilerDuty_kJ_per_kg;
  const cost = { deethanizer: columnInstalledCost_MUSD(COLUMN.deethanizer, deethanizer, p.plantCapacity_kt_per_y),
    depropanizer: columnInstalledCost_MUSD(COLUMN.depropanizer, depropanizer, p.plantCapacity_kt_per_y),
    debutanizer: columnInstalledCost_MUSD(COLUMN.debutanizer, debutanizer, p.plantCapacity_kt_per_y) };

  /* 8. Run length: t_run = 60 d exp(-0.025 (COT - 850)) (s/0.35)^0.6 (0.35/tau)^0.3 (assumption);
     on-stream factor = t_run/(t_run + 1.5 d decoking). */
  const runDays = DESIGN.runLengthReference_d * Math.exp(-0.025 * (p.coilOutletTemperature_C - 850)) * Math.pow(p.steamToEthane_kg_per_kg / 0.35, 0.6) * Math.pow(0.35 / p.residenceTime_s, 0.3);
  const onStreamFactor = runDays / (runDays + DESIGN.decoking_d);
  if (!Number.isFinite(runDays) || runDays <= 0) warnings.push('FAILED run length: zero on-stream time');
  const scale = (x, ref, e) => Math.pow(x / ref, e), C = CAPITAL;
  const tbmc = C.referenceTBMC_MUSD * scale(p.plantCapacity_kt_per_y, C.referenceCapacity_kt_per_y, C.capacityExponent) * (
      C.shareFurnace * scale(coilAreaUsed, FURNACE.referenceCoilArea_m2, C.furnaceExponent)
    + C.shareCompression * scale(compressorWork, C.referenceCompressorWork_kJ_per_kg, C.compressorExponent)
    + C.shareColdBox * scale(refrigerationWork, C.referenceColdBoxWork_kJ_per_kg, C.coldBoxExponent)
    + C.shareFractionation * scale(splitterReflux * Nact, C.referenceC2SplitterLoad, C.fractionationExponent))
    + COLUMN.costBasisFactor * (cost.deethanizer.installed_MUSD - COLUMN.deethanizerReferenceInstalledCost_MUSD + cost.depropanizer.installed_MUSD + cost.debutanizer.installed_MUSD);
  const tci = tbmc * C.tciPerTBMC, annualProduct_t = p.plantCapacity_kt_per_y * 1000 * onStreamFactor;

  /* 9. Production cost, USD/t ethylene. */
  const perGJ = 1e-3, electricity_USD_per_GJ = p.electricityPrice_USD_per_kWh / 0.0036;
  const costItems = {
    ethaneFeedMinimum: STOICHIOMETRIC_ETHANE_PER_ETHYLENE * p.ethanePrice_USD_per_t,
    ethaneFeedSelectivityLoss: (freshEthane - STOICHIOMETRIC_ETHANE_PER_ETHYLENE) * p.ethanePrice_USD_per_t,
    purchasedHeat: fired ? naturalGasBought * perGJ * p.naturalGasPrice_USD_per_GJ : electricHeat * perGJ * electricity_USD_per_GJ,
    processElectricity: (compressorWork + refrigerationWork + splitterWork + deethanizerWork) * perGJ * electricity_USD_per_GJ,
    columnSteamAndCoolingWater: reboilerSteam * perGJ * p.exportSteamPrice_USD_per_GJ + coolingWater * perGJ * DESIGN.coolingWaterCost_USD_per_GJ,
    steamCredit: -(tleSteam + convectionSteam) * perGJ * p.exportSteamPrice_USD_per_GJ,
    fuelGasCredit: -fuelGasSold * perGJ * p.naturalGasPrice_USD_per_GJ * p.fuelGasPriceFactor,
    c3PlusCredit: -(product.c3 + product.c4plus) * p.c3PlusPrice_USD_per_t,
    dilutionSteam: dilutionSteam * DESIGN.dilutionSteamLatentHeat_kJ_per_kg * perGJ * (p.exportSteamPrice_USD_per_GJ * DESIGN.dilutionSteamHeatGrade + DESIGN.coolingWaterCost_USD_per_GJ),
    capitalCharge: tci * 1e6 * p.capitalChargeFactor_per_y / annualProduct_t,
    operationMaintenanceLabor: (tci * 1e6 * C.omFractionOfTCI + p.labor_MUSD_per_y * 1e6) / annualProduct_t
  };
  const productionCost = Object.values(costItems).reduce((s, v) => s + v, 0);

  /* 10. Carbon intensity, kg CO2e/t ethylene (system expansion).
     Scope 1: natural gas 56.1 kg/GJ, burned fuel-gas methane and ethylene (stoichiometric CO2), column reboiler steam
     from a 90 % gas boiler (56.1/0.90 kg/GJ). Scope 2: electricity x grid factor. Scope 3: ethane upstream.
     Credits: TLE and convection steam (56.1/0.90 kg/GJ), sold fuel gas (56.1 kg/GJ of natural gas displaced),
     C3+ products (0.80 kg/kg). */
  const burnedFraction = fuelGas > 0 ? fuelGasBurned / fuelGas : 0;
  const electricity_kWh_per_kg = (compressorWork + refrigerationWork + splitterWork + deethanizerWork + electricHeat) * perGJ / 0.0036 / 1000;
  const scope1 = naturalGasBought * perGJ * 56.1
    + (product.methane * burnedFraction * 44.01 / 16.04 + ethyleneToFuelGas * burnedFraction * 2 * 44.01 / MOLAR_MASS.ethylene) * 1000
    + reboilerSteam * perGJ * 56.1 / 0.90;
  const scope2 = electricity_kWh_per_kg * 1000 * p.gridEmissionFactor_kg_per_kWh;
  const scope3 = freshEthane * p.ethaneUpstreamEmission_kg_per_kg * 1000;
  const steamCreditCarbon = -(tleSteam + convectionSteam) * perGJ * 56.1 / 0.90;
  const fuelGasCreditCarbon = fuelGasSurplus > 0 && p.fuelGasUse === 'sell' ? -fuelGasSold * perGJ * 56.1 : 0;
  const fuelGasBurnCarbon = fuelGasSurplus > 0 && p.fuelGasUse === 'burn'
    ? (product.methane * (1 - burnedFraction) * 44.01 / 16.04 + ethyleneToFuelGas * (1 - burnedFraction) * 2 * 44.01 / MOLAR_MASS.ethylene) * 1000 : 0;
  const c3PlusCreditCarbon = -(product.c3 + product.c4plus) * 0.80 * 1000;
  const carbonIntensity = scope1 + fuelGasBurnCarbon + scope2 + scope3 + steamCreditCarbon + c3PlusCreditCarbon + fuelGasCreditCarbon;

  return { inputs: p, warnings, reaction, gpSD, outsideTrainingRange, conversion, coilEthane, freshEthane, recycleEthane, dilutionSteam, product, acetyleneConverter,
    reactorDuty, purchasedHeat, naturalGasBought, fuelGas, fuelGasBurned, fuelGasSold, electricHeat, furnace, coilHeat, convectionSteam,
    compressorWork, refrigerationWork, splitterWork, deethanizerWork, reboilerSteam, coolingWater, columns: { deethanizer, depropanizer, debutanizer, cost },
    coldEnd_K: cb.coldEnd_K, runDays, onStreamFactor, tbmc, tci, annualProduct_t, costItems, productionCost,
    carbon: { scope1: scope1 + fuelGasBurnCarbon, scope2, scope3, steamCredit: steamCreditCarbon, c3PlusCredit: c3PlusCreditCarbon, fuelGasCredit: fuelGasCreditCarbon, total: carbonIntensity },
    electricity_kWh_per_kg };
}

/* ---------- Screen interface ----------
   The screen uses short keys (cot, tau, ...). toInputs() changes them to the model names. */
function toInputs(s) {
  const d = DEFAULT_INPUTS, v = (x, y) => (x === undefined || x === null || x === '' ? y : +x);
  return { ...d,
    heatSource: s.mode === 'JH' ? 'electric' : (s.mode === 'CH' ? 'fired' : d.heatSource),
    firedHeatModel: s.firedHeatModel || d.firedHeatModel,
    coilOutletTemperature_C: v(s.cot, d.coilOutletTemperature_C), residenceTime_s: v(s.tau, d.residenceTime_s),
    steamToEthane_kg_per_kg: v(s.dilution, d.steamToEthane_kg_per_kg), coilPressure_bar: v(s.pressure, d.coilPressure_bar),
    heatingExponent: v(s.ramp, d.heatingExponent), plantCapacity_kt_per_y: v(s.cap, d.plantCapacity_kt_per_y),
    ethanePrice_USD_per_t: v(s.ethane, d.ethanePrice_USD_per_t), naturalGasPrice_USD_per_GJ: v(s.gas, d.naturalGasPrice_USD_per_GJ),
    electricityPrice_USD_per_kWh: v(s.elec, d.electricityPrice_USD_per_kWh), exportSteamPrice_USD_per_GJ: v(s.steam, d.exportSteamPrice_USD_per_GJ),
    c3PlusPrice_USD_per_t: v(s.lpg, d.c3PlusPrice_USD_per_t), gridEmissionFactor_kg_per_kWh: v(s.grid, d.gridEmissionFactor_kg_per_kWh),
    ethaneUpstreamEmission_kg_per_kg: v(s.ethaneUp, d.ethaneUpstreamEmission_kg_per_kg),
    firedEfficiencyFixed_percent: s.mode === 'CH' ? v(s.eff, d.firedEfficiencyFixed_percent) : d.firedEfficiencyFixed_percent,
    electricEfficiency_percent: s.mode === 'JH' ? v(s.eff, d.electricEfficiency_percent) : d.electricEfficiency_percent };
}
/* Output for the screen. Names are those the screen reads. */
function evaluate(state = {}) {
  const r = calculatePlant(toInputs(state)), ci = r.costItems;
  return {
    conversion: r.conversion, selectivity_mass: r.reaction.y_c2h4_kg_per_kg_ethane / Math.max(r.conversion, 1e-12),
    fresh_ethane_kg_per_kg: r.freshEthane, coil_ethane_kg_per_kg: r.coilEthane, recycle_ethane_kg_per_kg: r.recycleEthane, steam_kg_per_kg: r.dilutionSteam,
    ch4_kg_per_kg: r.product.methane, h2_kg_per_kg: r.product.hydrogen, c2h2_kg_per_kg: r.product.acetyleneLeft,
    c3_kg_per_kg: r.product.c3, c4plus_kg_per_kg: r.product.c4plus, c5plus_kg_per_kg: r.product.c5plus,
    acetylene_converter: { ...r.acetyleneConverter },
    heavy_ends: { reboiler_steam_gj_per_t: r.reboilerSteam / 1000, cooling_water_gj_per_t: r.coolingWater / 1000 },
    deethanizer_kwh_per_t: r.deethanizerWork / 3.6,
    reactor_useful_heat_gj_per_t: r.reactorDuty / 1000, heater_input_gj_per_t: r.purchasedHeat / 1000,
    purchased_natural_gas_gj_per_t: r.naturalGasBought / 1000, convection_steam_gj_per_t: r.convectionSteam / 1000,
    furnace: r.furnace, coil_heat: r.coilHeat,
    compressor_kwh_per_t: r.compressorWork / 3.6, refrigeration_kwh_per_t: r.refrigerationWork / 3.6, splitter_kwh_per_t: r.splitterWork / 3.6,
    total_process_power_kwh_per_t: r.electricity_kWh_per_kg * 1000,
    cost_usd_per_t: r.productionCost, carbon_kgco2e_per_t: r.carbon.total, carbon_scopes_kgco2e_per_t: { scope1: r.carbon.scope1, scope2: r.carbon.scope2, scope3: r.carbon.scope3 },
    annual_product_kt: r.annualProduct_t / 1000, toc_musd: r.tci, tbmc_musd: r.tbmc, run_days: r.runDays,
    cost_breakdown_usd_per_t: { floor: ci.ethaneFeedMinimum, selLoss: ci.ethaneFeedSelectivityLoss, heat: ci.purchasedHeat, elecProc: ci.processElectricity,
      heavyEnds: ci.columnSteamAndCoolingWater, steamCr: ci.steamCredit, gasCr: ci.fuelGasCredit, lpgCr: ci.c3PlusCredit, dilSteam: ci.dilutionSteam,
      capital: ci.capitalCharge, om: ci.operationMaintenanceLabor },
    gp_mean: { ...r.reaction }, gp_sd: r.gpSD ? { ...r.gpSD } : null, outside_training_range: r.outsideTrainingRange,
    flags: [...r.warnings]
  };
}

/* ---------- Analysis tools ----------
   The analysis tools change the heat source themselves. The screen state carries one efficiency for its own heat
   source, so withoutEfficiency() removes it; each heat source then uses its own default efficiency. */
const withoutEfficiency = state => { const s = { ...state }; delete s.eff; return s; };
/* Break-even electricity price (USD/kWh): electric and fired production cost are equal at the same condition. */
function breakEven(stateIn = {}) {
  const state = withoutEfficiency(stateIn);
  const f = e => evaluate({ ...state, mode: 'CH', elec: e }).cost_usd_per_t, j = e => evaluate({ ...state, mode: 'JH', elec: e }).cost_usd_per_t;
  let lo = 1e-4, hi = 0.5;
  for (let i = 0; i < 60; i++) { const m = (lo + hi) / 2; if (j(m) > f(m)) hi = m; else lo = m; }
  const F = calculatePlant(toInputs({ ...state, mode: 'CH' })), J = calculatePlant(toInputs({ ...state, mode: 'JH' }));
  const grid = toInputs(state).gridEmissionFactor_kg_per_kWh;
  return { electricity_usd_per_kwh: (lo + hi) / 2,
    grid_kg_per_kwh: grid - (J.carbon.total - F.carbon.total) / ((J.electricity_kWh_per_kg - F.electricity_kWh_per_kg) * 1000) };
}
/* Plant checks: one model number against one published number; OK within 10 %. */
function plantChecks(state = {}) {
  const out = [], add = (name, model, published, unit, source) => { const d = (model - published) / published;
    out.push({ name, model_value: model, published, unit, deviation: d, status: Math.abs(d) <= 0.10 ? 'OK' : 'FAILED', source }); };
  const msf = { ...state, mode: 'CH', cot: 882, tau: 0.25, dilution: 0.5, pressure: 1.7, ramp: 1 };
  const m = predictReaction(toInputs(msf)).mean;
  add('Ethane conversion, Millisecond Furnace', m.x_c2h6, 0.55, '-', 'US 2025/0277154 A1 Table 2');
  add('Ethylene mass selectivity, Millisecond Furnace', m.y_c2h4_kg_per_kg_ethane / m.x_c2h6, 0.86, '-', 'US 2025/0277154 A1 Table 2');
  const ethanePerCoil_kg_s = 37000 * 0.45359237 / 3600 / 152;   // 37,000 lb/h ethane over 152 coils
  const duty = (m.heat_MJ_per_kg_ethane * 1000 - (DESIGN.ethaneHeatCapacity_kJ_per_kgK + 0.5 * DESIGN.steamHeatCapacity_kJ_per_kgK) * (705 - 650)) * ethanePerCoil_kg_s;
  add('Radiant duty per coil from a 705 degC inlet', duty, 105, 'kW', 'US 2025/0277154 A1 Table 2');
  // Inside-wall temperature, Dittus-Boelter film coefficient, no fitted value:
  // h = 0.023 Re^0.8 Pr^0.4 k/d; gas at the mean condition (793.5 degC, 1.7 bar, 27.5 % converted), Cantera 3.2
  // GRI-Mech 3.0 transport: viscosity 3.16e-5 Pa s, conductivity 0.165 W/m K, heat capacity 3593 J/kg K.
  const d = 0.0381, G = ethanePerCoil_kg_s * 1.5 / (Math.PI * d * d / 4), mu = 3.16e-5, k = 0.165, cp = 3593;
  const h = 0.023 * Math.pow(G * d / mu, 0.8) * Math.pow(cp * mu / k, 0.4) * k / d, q = 105e3 / (Math.PI * d * 42 * 0.3048);
  add('Inside-wall mean temperature (Dittus-Boelter, no fit)', 793.5 + q / h, 970, 'degC', 'US 2025/0277154 A1 Table 2');
  add('Inside-wall maximum temperature (Dittus-Boelter, no fit)', 882 + q / h, 1099, 'degC', 'US 2025/0277154 A1 Table 2');
  add('Ethane conversion, Example 2 (915 degC exit, fixed wall temperature)', predictReaction(toInputs({ ...msf, cot: 915 })).mean.x_c2h6, 0.60, '-', 'US 2025/0277154 A1 Table 2');
  return { checks: out, dittusBoelterFilm_W_per_m2K: h };
}
/* Shadow price of each product: change of cost and carbon per 1 kg of the product per kg ethylene.
   One product changes by 0.001 kg/kg; ethylene yield, conversion and other products stay fixed. The ethane feed
   that a real shift needs is not included. Recycle ethane: more coil ethane, same fresh ethane and products. */
const COST_ITEM_WORDS = { ethaneFeedMinimum: 'ethane feed, minimum', ethaneFeedSelectivityLoss: 'ethane feed, selectivity loss',
  purchasedHeat: 'purchased heat', processElectricity: 'process electricity', columnSteamAndCoolingWater: 'column steam and cooling water',
  steamCredit: 'steam credit', fuelGasCredit: 'fuel gas credit', c3PlusCredit: 'C3+ credit', dilutionSteam: 'dilution steam',
  capitalCharge: 'capital charge', operationMaintenanceLabor: 'operation, maintenance and labor' };
function shadowPrices(state = {}) {
  const inputs = toInputs(state), base = calculatePlant(inputs), coil = base.coilEthane;
  const m0 = { ...base.reaction, y_c5plus_kg_per_kg_ethane: base.product.c5plus / coil };
  const run = m => { directComposition = m; try { return calculatePlant(inputs); } finally { directComposition = null; } };
  const ref = run(m0), dy = 0.001, rows = [];
  const one = (name, change, denominator) => { const o = run(change({ ...m0 })), den = denominator ? denominator(o) : dy, items = {};
    for (const key of Object.keys(o.costItems)) { const v = (o.costItems[key] - ref.costItems[key]) / den; if (Math.abs(v) > 0.05) items[COST_ITEM_WORDS[key]] = v; }
    rows.push({ lump: name, cost_USD_per_t_per_kg_per_kg: (o.productionCost - ref.productionCost) / den, carbon_kg_per_t_per_kg_per_kg: (o.carbon.total - ref.carbon.total) / den, items }); };
  one('H2', m => (m.y_h2_kg_per_kg_ethane += dy / coil, m));
  one('CH4', m => (m.y_ch4_kg_per_kg_ethane += dy / coil, m));
  one('C2H2', m => (m.y_c2h2_kg_per_kg_ethane += dy / coil, m));
  one('C3', m => (m.y_c3_kg_per_kg_ethane += dy / coil, m));
  one('C4', m => (m.y_c4plus_kg_per_kg_ethane += dy / coil, m));
  one('C5+', m => (m.y_c4plus_kg_per_kg_ethane += dy / coil, m.y_c5plus_kg_per_kg_ethane += dy / coil, m));
  const dR = 0.01, k = coil / (coil + dR);
  one('C2H6 recycle', m => { for (const key of Object.keys(m)) if (/^y_/.test(key) && key !== 'y_c2h6_kg_per_kg_ethane') m[key] *= k;
      m.x_c2h6 = m0.x_c2h6 * k; m.y_c2h6_kg_per_kg_ethane = 1 - m.x_c2h6;
      m.heat_MJ_per_kg_ethane = m0.heat_MJ_per_kg_ethane * k + (1 - k) * (DESIGN.ethaneHeatCapacity_kJ_per_kgK + inputs.steamToEthane_kg_per_kg * DESIGN.steamHeatCapacity_kJ_per_kgK) * (inputs.coilOutletTemperature_C - 650) / 1000;
      return m; }, o => o.recycleEthane - ref.recycleEthane);
  return rows;
}
/* Fired against electric: (a) fired at its lowest-cost condition, (b) electric at the same condition,
   (c) electric at its lowest-cost condition. Grid: COT 780-950 degC (10 K), residence time 0.05-1.5 s (13 points). */
function bestCondition(state, mode) {
  let best = null;
  for (let T = 780; T <= 950; T += 10) for (let i = 0; i <= 12; i++) {
    const tau = 0.05 * Math.pow(1.5 / 0.05, i / 12), r = calculatePlant(toInputs({ ...state, mode, cot: T, tau }));
    if (!Number.isFinite(r.productionCost) || (mode === 'CH' && r.coilHeat.tmtStatus === 'FAILED')) continue;
    if (!best || r.productionCost < best.r.productionCost) best = { cot: T, tau, r };
  }
  return best;
}
function waterfall(stateIn = {}) {
  const state = withoutEfficiency(stateIn);
  const a = bestCondition(state, 'CH'), c = bestCondition(state, 'JH');
  const b = { cot: a.cot, tau: a.tau, r: calculatePlant(toInputs({ ...state, mode: 'JH', cot: a.cot, tau: a.tau })) };
  const describe = s => ({ COT_C: s.cot, residence_time_s: s.tau, cost_USD_per_t: s.r.productionCost, carbon_kg_per_t: s.r.carbon.total,
    conversion: s.r.conversion, ethylene_yield_kg_per_kg_coil: s.r.reaction.y_c2h4_kg_per_kg_ethane, methane_kg_per_kg_ethylene: s.r.product.methane,
    acetylene_kg_per_kg_ethylene: s.r.acetyleneConverter.rawKg, C4plus_kg_per_kg_ethylene: s.r.product.c4plus, recycle_kg_per_kg: s.r.recycleEthane,
    tube_metal_status: s.r.coilHeat.tmtStatus });
  const diff = (u, v) => { const o = {}; for (const k of Object.keys(u.r.costItems)) { const d = v.r.costItems[k] - u.r.costItems[k]; if (Math.abs(d) > 0.05) o[COST_ITEM_WORDS[k]] = d; } return o; };
  return { fired_best: describe(a), electric_same_condition: describe(b), electric_best: describe(c), step_a_to_b: diff(a, b), step_b_to_c: diff(b, c) };
}
/* Input table shown on the screen: name, value, unit, range, source. */
const INPUT_TABLE = [
  ['Ethane price', DEFAULT_INPUTS.ethanePrice_USD_per_t, 'USD/t', '150-350', 'Mittal et al. 2025 SI'],
  ['Natural-gas price', DEFAULT_INPUTS.naturalGasPrice_USD_per_GJ, 'USD/GJ LHV', '2-8', 'EIA 2024 US industrial'],
  ['Electricity price', DEFAULT_INPUTS.electricityPrice_USD_per_kWh, 'USD/kWh', '0.01-0.12', 'scenario; EIA 2024 Texas, Louisiana'],
  ['Export-steam price', DEFAULT_INPUTS.exportSteamPrice_USD_per_GJ, 'USD/GJ', '3-10', 'natural-gas price / 0.90 boiler (Towler and Sinnott 2013)'],
  ['C3+ product price', DEFAULT_INPUTS.c3PlusPrice_USD_per_t, 'USD/t', '161-740', 'Mittal et al. 2025 SI'],
  ['Fuel-gas price factor', DEFAULT_INPUTS.fuelGasPriceFactor, '- of gas price', '0-1', 'assumption'],
  ['Grid emission factor', DEFAULT_INPUTS.gridEmissionFactor_kg_per_kWh, 'kg CO2e/kWh', '0-0.8', 'US 2023 average'],
  ['Electric heating efficiency', DEFAULT_INPUTS.electricEfficiency_percent, '%', '80-98', 'Mittal et al. 2025 SI'],
  ['Excess air', FURNACE.excessAirFraction, '-', '0.05-0.20', 'assumption'],
  ['Bridgewall temperature', FURNACE.bridgewallTemperature_C, 'degC', '1000-1250', 'US 11,913,362 (about 1100 degC)'],
  ['Stack temperature', FURNACE.stackTemperature_C, 'degC', '110-180', 'assumption'],
  ['Tube metal limit', FURNACE.tubeMetalLimit_C, 'degC', '1100-1150', 'US 8,747,765 B2'],
  ['Coil inside diameter', FURNACE.coilInsideDiameter_m, 'm', '0.02-0.16', 'US 2025/0277154 A1'],
  ['Ethylene recovery', DESIGN.ethyleneRecovery, '-', '0.99-0.999', 'design specification'],
  ['Compressor discharge', DESIGN.compressorDischarge_bar, 'bar', '25-35', 'design value'],
  ['TLE heat recovery', DESIGN.tleRecoveryFraction, '-', '0.5-0.9', 'assumption'],
  ['Column key recovery / reflux factor', COLUMN.keyRecovery + ' / ' + COLUMN.refluxFactor, '-', '-', 'Towler and Sinnott 2022'],
  ['Reference bare-module cost', CAPITAL.referenceTBMC_MUSD, 'MUSD at 610 kt/y', '-', 'Mittal et al. 2025 SI'],
  ['Capital charge / O&M', DEFAULT_INPUTS.capitalChargeFactor_per_y + ' / ' + CAPITAL.omFractionOfTCI, '1/y / - of TCI', '-', 'Mittal et al. 2025 SI']
];

return {
  loadGP, status: () => gpStatus, ready: () => !!gpParameters,
  metadata: () => ({ training_points: gpParameters ? gpParameters.training_points : null,
    validation_points: gpValidation ? gpValidation.validation_points : null,
    domain_min: gpParameters ? [...gpParameters.domain_min] : null, domain_max: gpParameters ? [...gpParameters.domain_max] : null,
    source: gpParameters && gpParameters.source ? { cantera_version: gpParameters.source.cantera_version, mechanism_species: gpParameters.source.mechanism_species,
      mechanism_reactions: gpParameters.source.mechanism_reactions, mechanism_provenance: gpParameters.source.mechanism_provenance } : null,
    validation: gpValidation ? { passed: gpValidation.passed, outputs: gpValidation.outputs } : null }),
  defaults: () => ({ ...DEFAULT_INPUTS }),
  evaluate, calculatePlant, toInputs,
  analysis: { breakEven, plantChecks, shadowPrices, waterfall, inputTable: INPUT_TABLE }
};
})();
if (typeof window !== 'undefined') window.ethaneModel = EthaneCrackerModel;
if (typeof module !== 'undefined') module.exports = EthaneCrackerModel;
