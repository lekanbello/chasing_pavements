"""
sensitivity_scale.py — Welfare sensitivity to trade cost normalization scale.

For each scale value, re-calibrate the model and run Stage 1 counterfactual.
Shows that welfare gains are robust to the choice of normalization.

Note: under the v2 calibration the headline scale is whatever brentq picks to
hit median π_nn = 0.4. This script overrides that to test sensitivity.

Usage:
    python3 src/sensitivity_scale.py
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import json
import io
import contextlib
import geopandas as gpd

from calibrate import prepare_distances, invert_model

# Load data
admin = gpd.read_file('data/processed/tanzania_calibrated.gpkg')
tc_base = np.load('data/processed/tanzania_trade_costs_baseline.npy')
tc_cf = np.load('data/processed/tanzania_trade_costs_counterfactual.npy')

with open('data/processed/tanzania_model_params.json') as f:
    params = json.load(f)

sigma = params["parameters"]["sigma"]
alpha = params["parameters"]["alpha"]
kappa = params["parameters"]["kappa"]
n_full = len(admin)

L_full = admin["population"].values
Y_full = admin["gdp_usd"].values

# Filter districts
keep = np.ones(n_full, dtype=bool)
for i in range(n_full):
    name = admin.iloc[i]["NAME_2"]
    if any(w in name.lower() for w in ["lake ", "mafia"]):
        keep[i] = False
    if L_full[i] < 1000:
        keep[i] = False
    row = tc_base[i, :]
    if not (np.isfinite(row) & (np.arange(n_full) != i) & (row > 0)).any():
        keep[i] = False

idx = np.where(keep)[0]
nn = len(idx)
L = L_full[idx]
Y = Y_full[idx]
tc_b = tc_base[np.ix_(idx, idx)]
tc_c = tc_cf[np.ix_(idx, idx)]

w = Y / L
lam = L / L.sum()
wl = w * lam


def calibrate_and_solve(tc_b, scale, L, Y, kappa, alpha, sigma):
    """Calibrate at a given scale and run Stage 1 counterfactual.
    Returns (median_pi_nn, welfare_pct_stage1)."""
    distances = prepare_distances(tc_b)
    tau = 1.0 + distances / scale
    np.fill_diagonal(tau, 1.0)
    with contextlib.redirect_stdout(io.StringIO()):
        A, _, _, pi = invert_model(L, Y, tau, sigma=sigma, kappa=kappa,
                                   alpha=alpha, max_iter=2000, tol=1e-3)
    pi_nn = np.diag(pi)

    # d_hat (Bug 1 fix: τ-ratio)
    nn = len(L)
    connected = np.isfinite(tc_b) & np.isfinite(tc_c) & (tc_b > 0) & (tc_c > 0)
    np.fill_diagonal(connected, True)
    d_hat = np.ones((nn, nn))
    mask = connected & ~np.eye(nn, dtype=bool)
    d_hat[mask] = (1.0 + tc_c[mask] / scale) / (1.0 + tc_b[mask] / scale)

    # Stage 1 solver
    w_hat = np.ones(nn)
    for it in range(3000):
        w_hat_old = w_hat.copy()
        factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma)
        num = pi * factor
        pi_p = num / num.sum(axis=1, keepdims=True)
        rhs = pi_p.T @ (w_hat * wl)
        w_hat_new = rhs / np.maximum(wl, 1e-300)
        w_hat = w_hat**0.7 * np.maximum(w_hat_new, 1e-20)**0.3
        w_hat = w_hat / np.average(w_hat, weights=wl)
        if np.max(np.abs(np.log(w_hat) - np.log(w_hat_old))) < 1e-6:
            break

    pi_nn_p = np.diag(pi_p)
    exp1 = alpha / (sigma - 1)
    # Bug 5 fix: drop leading ŵ
    welfare_loc = (pi_nn / np.maximum(pi_nn_p, 1e-20))**exp1
    welfare = float(np.average(welfare_loc, weights=L))
    return float(np.median(pi_nn)), 100 * (welfare - 1)


print(f"Districts: {nn}")
print(f"\n{'='*60}")
print(f"WELFARE SENSITIVITY TO TRADE COST SCALE — v2")
print(f"{'='*60}")
print(f"{'Scale':>8s} {'Med pi_nn':>10s} {'Welfare':>10s} {'Note':>25s}")
print(f"{'-'*55}")

# Use the calibrated v2 scale as the central reference, plus a wide range.
v2_scale = int(params.get("trade_cost_scale", 263))
scales = sorted(set([v2_scale, 100, 200, 500, 1000, 2000, 5000]))

results = []
for scale in scales:
    med_pi, welf = calibrate_and_solve(tc_b, scale, L, Y, kappa, alpha, sigma)
    note = ""
    if scale == v2_scale:
        note = "v2 calibration (pi_nn=0.4)"
    print(f"{scale:>8d} {med_pi:>10.3f} {welf:>+10.1f}% {note:>25s}")
    results.append({"scale": scale, "pi_nn": med_pi, "welfare_pct": welf})

# Save
with open('outputs/welfare_sensitivity_scale.txt', 'w') as f:
    f.write("Welfare Sensitivity to Trade Cost Scale (Stage 1) — v2\n")
    f.write(f"Country: Tanzania, n={nn}, sigma={sigma}, alpha={alpha}\n")
    f.write("=" * 55 + "\n")
    for r in results:
        f.write(f"scale={r['scale']:>5d}: pi_nn={r['pi_nn']:.3f}, welfare={r['welfare_pct']:+.1f}%\n")

print(f"\nSaved to outputs/welfare_sensitivity_scale.txt")
