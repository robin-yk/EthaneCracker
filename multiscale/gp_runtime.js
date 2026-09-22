"use strict";

/*
 * Zero-dependency browser runtime for surrogate.json produced by train_gp.py.
 * The runtime exposes raw GP means and calibrated posterior uncertainty. It never
 * silently clips chemically impossible predictions; physical violations are returned
 * as warnings so the UI / TEA layer can block or flag them.
 */

export class EthaneGPSurrogate {
  constructor(model) {
    this.m = model;
    if (model.schema !== "ethane-cantera-shared-rbf-gp-v3") {
      throw new Error("Unsupported surrogate schema: " + model.schema);
    }
  }

  static async load(url = "./surrogate.json") {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`Could not load ${url} (HTTP ${r.status})`);
    return new EthaneGPSurrogate(await r.json());
  }

  _rawVector(p) {
    const tau = Number(p.residence_time_s);
    if (!(tau > 0)) throw new Error("residence_time_s must be > 0");
    return [
      Number(p.temperature_c),
      Math.log10(tau),
      Number(p.steam_hc_kgkg),
      Number(p.pressure_bar),
      Number(p.ramp_exponent),
    ];
  }

  _normalize(raw) {
    return raw.map((v, j) => (v - this.m.x_min[j]) / (this.m.x_max[j] - this.m.x_min[j]));
  }

  domain(p) {
    const raw = this._rawVector(p);
    const lo = this.m.domain_min || this.m.x_min;
    const hi = this.m.domain_max || this.m.x_max;
    const outside = [];
    raw.forEach((v, j) => {
      if (v < lo[j] || v > hi[j]) {
        outside.push({
          input: this.m.inputs[j],
          value: v,
          min: lo[j],
          max: hi[j],
        });
      }
    });
    return { inside: outside.length === 0, outside };
  }

  _physicalWarnings(mean) {
    const w = [];
    const bounded01 = ["x_c2h6", "s_c2h4_mol"];
    for (const k of bounded01) {
      if (k in mean && (mean[k] < 0 || mean[k] > 1)) {
        w.push(`${k}=${mean[k]} is outside [0,1]`);
      }
    }
    for (const [k, v] of Object.entries(mean)) {
      if (k.startsWith("y_") && k.endsWith("_kg_per_kg_ethane") && v < -1e-8) {
        w.push(`${k}=${v} is negative`);
      }
    }
    if ("heat_MJ_per_kg_ethane" in mean && !Number.isFinite(mean.heat_MJ_per_kg_ethane)) {
      w.push("heat prediction is non-finite");
    }
    return w;
  }

  predict(p) {
    const raw = this._rawVector(p);
    const x = this._normalize(raw);
    const n = this.m.x_train.length;
    const d = x.length;
    const k = new Array(n);

    for (let i = 0; i < n; i++) {
      let q = 0;
      const xi = this.m.x_train[i];
      for (let j = 0; j < d; j++) {
        const z = (x[j] - xi[j]) / this.m.length_scale[j];
        q += z * z;
      }
      k[i] = Math.exp(-0.5 * q);
    }

    const latent = [];
    const out = {};
    const deriv = [];
    for (let o = 0; o < this.m.outputs.length; o++) {
      let zstd = 0;
      for (let i = 0; i < n; i++) zstd += k[i] * this.m.alpha[i][o];
      const z = this.m.y_mean[o] + this.m.y_std[o] * zstd;
      latent[o] = z;
      const spec = this.m.output_transforms[o];
      if (spec.kind === "logit") {
        const p = z >= 0 ? 1 / (1 + Math.exp(-z)) : Math.exp(z) / (1 + Math.exp(z));
        out[this.m.outputs[o]] = p;
        deriv[o] = p * (1 - p);
      } else if (spec.kind === "log") {
        const ez = Math.exp(z);
        out[this.m.outputs[o]] = Math.max(0, ez - spec.epsilon);
        deriv[o] = ez;
      } else {
        throw new Error("Unsupported output transform " + spec.kind);
      }
    }

    let quad = 0;
    for (let i = 0; i < n; i++) {
      let row = 0;
      const ki = this.m.k_inv[i];
      for (let j = 0; j < n; j++) row += ki[j] * k[j];
      quad += k[i] * row;
    }
    const sigmaStd = Math.sqrt(Math.max(0, 1 - quad));
    const sigma = {};
    for (let o = 0; o < this.m.outputs.length; o++) {
      const scale = this.m.sigma_scale ? this.m.sigma_scale[o] : 1;
      sigma[this.m.outputs[o]] = sigmaStd * this.m.y_std[o] * deriv[o] * scale;
    }

    const domain = this.domain(p);
    const physicalWarnings = this._physicalWarnings(out);
    return {
      mean: out,
      sigma,
      standardized_sigma: sigmaStd,
      domain,
      physical_warnings: physicalWarnings,
      qualified: domain.inside && physicalWarnings.length === 0,
      training_points: this.m.training_points,
      source: this.m.source,
    };
  }
}
