#!/usr/bin/env python3
"""Small numerical smoke test for the shared-kernel GP algebra."""

import numpy as np


def rbf(xa, xb, length):
    d = (xa[:, None, :] - xb[None, :, :]) / length[None, None, :]
    return np.exp(-0.5 * np.sum(d * d, axis=2))


def main():
    rng = np.random.default_rng(3)
    x = rng.random((40, 5))
    y = np.column_stack(
        [
            np.sin(2 * x[:, 0]) + 0.2 * x[:, 1],
            x[:, 2] * x[:, 3] + 0.1 * x[:, 4],
        ]
    )
    ym, ys = y.mean(0), y.std(0)
    yz = (y - ym) / ys
    length = np.full(5, 0.32)
    k = rbf(x, x, length)
    k.flat[:: len(k) + 1] += 1e-8
    l = np.linalg.cholesky(k)
    alpha = np.linalg.solve(l.T, np.linalg.solve(l, yz))
    pred = (k @ alpha) * ys + ym
    mae = np.abs(pred - y).mean(0)
    assert np.all(mae < 1e-5), mae

    linv = np.linalg.solve(l, np.eye(len(k)))
    kinv = linv.T @ linv
    k0 = rbf(x[:1], x, length)[0]
    var0 = max(0.0, 1.0 - k0 @ kinv @ k0)
    assert var0 < 1e-5, var0
    print("PASS shared-kernel GP algebra", "MAE", mae, "train variance", var0)


if __name__ == "__main__":
    main()
