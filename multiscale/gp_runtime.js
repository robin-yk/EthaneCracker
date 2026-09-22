"use strict";

/*
 * Zero-dependency browser runtime for surrogate.json produced by train_gp.py.
 * Mean prediction is exact for the exported shared-kernel GP. Predictive sigma
 * is the GP posterior standard deviation in each output's original units.
 */

export class EthaneGPSurrogate {
  constructor(model) {
    this.m = model;
    if (model.schema !== "ethane-cantera-shared-rbf-gp-v1") {
      throw new Error("Unsupported surrogate schema: " + model.schema);
    }
  }

  static async load(url = "./surrogate.json") {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) throw new Error(`Could not load ${url} (HTTP ${r.status})`);
    return new EthaneGPSurrogate(await r.json());
  }

  _rawVector(p) {
    return [
      Number(p.temperature_c),
      Math.log10(Number(p.residence_time_s)),
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
    const outside = [];
    raw.forEach((v, j) => {
      if (v < this.m.x_min[j] || v > this.m.x_max[j]) {
        outside.push({
          input: this.m.inputs[j],
          value: v,
          min: this.m.x_min[j],
          max: this.m.x_max[j],
        });
      }
    });
    return { inside: outside.length === 0, outside };
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

    const out = {};
    for (let o = 0; o < this.m.outputs.length; o++) {
      let z = 0;
      for (let i = 0; i < n; i++) z += k[i] * this.m.alpha[i][o];
      out[this.m.outputs[o]] = this.m.y_mean[o] + this.m.y_std[o] * z;
    }

    // k(x,x)=1 for the unit-amplitude RBF prior.
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
      sigma[this.m.outputs[o]] = sigmaStd * this.m.y_std[o];
    }

    return {
      mean: out,
      sigma,
      standardized_sigma: sigmaStd,
      domain: this.domain(p),
      training_points: this.m.training_points,
      source: this.m.source,
    };
  }
}
