"""
sensitivity_sigma_c.py — Welfare sensitivity to σ and c parameters.

Varies the elasticity of substitution (σ) and unpaved cost ratio (c)
across a grid and reports welfare gains for each combination.
"""

import numpy as np
import json
import geopandas as gpd

# Load data
admin = gpd.read_file("data/processed/tanzania_calibrated.gpkg")
tc_base_orig = np.load("data/processed/tanzania_trade_costs_baseline.npy")
tc_cf = np.load("data/processed/tanzania_trade_costs_counterfactual.npy")

with open("data/processed/tanzania_model_params.json") as f:
    params = json.load(f)

alpha = params["parameters"]["alpha"]
theta_base = params["parameters"]["theta"]
n_full = len(admin)

L_full = admin["population"].values
Y_full = admin["gdp_usd"].values

# Filter districts (same as counterfactual.py)
keep = np.ones(n_full, dtype=bool)
for i in range(n_full):
    name = admin.iloc[i]["NAME_2"]
    if any(w in name.lower() for w in ["lake ", "mafia"]):
        keep[i] = False
    if L_full[i] < 1000:
        keep[i] = False
    row = tc_base_orig[i, :]
    if not (np.isfinite(row) & (np.arange(n_full) != i) & (row > 0)).any():
        keep[i] = False

idx = np.where(keep)[0]
nn = len(idx)
L = L_full[idx]
Y = Y_full[idx]
tc_b_orig = tc_base_orig[np.ix_(idx, idx)]
tc_c = tc_cf[np.ix_(idx, idx)]

w = Y / L
lam = L / L.sum()
wl = w * lam

print(f"Districts: {nn}")
print(f"Running sensitivity grid: σ × c\n")

# Parameter grids
sigmas = [3, 4, 5, 6, 7]
c_ratios = [2.0, 2.5, 3.0, 3.5, 4.0]

results = np.zeros((len(c_ratios), len(sigmas)))

for ci, c_new in enumerate(c_ratios):
    for si, sigma in enumerate(sigmas):
        # Rescale baseline for new c
        # tc_cf has all roads at c=1. tc_base_orig has c=3.
        # The unpaved portion = tc_base_orig - tc_cf
        # New baseline = tc_cf + (tc_base_orig - tc_cf) * (c_new / 3.0)
        tc_b = tc_c + (tc_b_orig - tc_c) * (c_new / 3.0)

        # d_hat
        conn = np.isfinite(tc_b) & np.isfinite(tc_c) & (tc_b > 0) & (tc_c > 0)
        np.fill_diagonal(conn, True)
        d_hat = np.ones((nn, nn))
        mask = conn & ~np.eye(nn, dtype=bool)
        d_hat[mask] = tc_c[mask] / tc_b[mask]
        np.fill_diagonal(d_hat, 1.0)

        # Trade cost normalization
        tc_copy = tc_b.copy()
        finite = np.isfinite(tc_copy) & (tc_copy > 0)
        max_f = tc_copy[finite].max() if finite.any() else 1.0
        tc_copy[~np.isfinite(tc_copy)] = max_f * 2
        np.fill_diagonal(tc_copy, 0)
        off = tc_copy[~np.eye(nn, dtype=bool) & (tc_copy > 0)]
        scale = np.median(off) / 4.0 if len(off) > 0 else 340

        tau = 1.0 + tc_copy / scale
        np.fill_diagonal(tau, 1.0)

        # Compute trade shares with current sigma
        # Use productivities from base calibration (approximate)
        A = admin.iloc[idx]["productivity"].values
        cost = np.outer(w**alpha, np.ones(nn)) * tau
        num = np.outer(A**sigma, np.ones(nn)) * cost**(-sigma)
        Phi = num.sum(axis=0)
        Phi = np.maximum(Phi, 1e-300)
        pi = num / Phi[np.newaxis, :]

        pi_nn = np.diag(pi)

        # Stage 1 solver (fixed population)
        w_hat = np.ones(nn)
        for it in range(3000):
            w_hat_old = w_hat.copy()
            factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma)
            num_cf = pi * factor
            pi_p = num_cf / num_cf.sum(axis=1, keepdims=True)
            rhs = pi_p.T @ (w_hat * wl)
            w_hat_new = rhs / wl
            w_hat = w_hat**0.7 * np.maximum(w_hat_new, 1e-20)**0.3
            w_hat = w_hat / np.average(w_hat, weights=wl)
            if np.max(np.abs(np.log(w_hat) - np.log(w_hat_old))) < 1e-6:
                break

        # Welfare
        pi_nn_p = np.diag(pi_p)
        exp1 = alpha / (sigma - 1)
        welfare = np.average(w_hat * (pi_nn / np.maximum(pi_nn_p, 1e-20))**exp1, weights=L)
        welf_pct = 100 * (welfare - 1)
        results[ci, si] = welf_pct

        print(f"  σ={sigma}, c={c_new}: welfare = {welf_pct:+.1f}%")

# Print table
print(f"\n{'='*70}")
print(f"WELFARE SENSITIVITY TABLE (Stage 1, fixed population)")
print(f"{'='*70}")
label = 'c \\ σ'
header = f"{label:>8s}" + "".join(f"{s:>10d}" for s in sigmas)
print(header)
print("-" * len(header))
for ci, c in enumerate(c_ratios):
    row = f"{c:>8.1f}" + "".join(f"{results[ci,si]:>+10.1f}%" for si in range(len(sigmas)))
    print(row)

# Save
with open("outputs/welfare_sensitivity_sigma_c.txt", "w") as f:
    f.write("Welfare Sensitivity to sigma and c (Stage 1, fixed population)\n")
    f.write(f"Country: Tanzania, n={nn} districts, alpha={alpha}\n")
    f.write("=" * 60 + "\n")
    f.write(header + "\n")
    f.write("-" * len(header) + "\n")
    for ci, c in enumerate(c_ratios):
        row = f"{c:>8.1f}" + "".join(f"{results[ci,si]:>+10.1f}%" for si in range(len(sigmas)))
        f.write(row + "\n")

print(f"\nSaved to outputs/welfare_sensitivity_sigma_c.txt")
