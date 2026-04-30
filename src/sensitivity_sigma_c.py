"""
sensitivity_sigma_c.py — Welfare sensitivity to σ and c parameters.

For each (σ, c) on the grid, re-invert calibration with that σ and re-run
the Stage-1 counterfactual. Note that varying σ requires a fresh calibration
(productivities A solved under that σ), not just re-using the headline A.

This is the corrected v2 version of the script:
- Krugman-CES inversion (matches Phase 3) with row-stochastic π
- d_hat = τ-ratio (1 + tc'/scale) / (1 + tc/scale)
- Stage-1 welfare formula has no leading ŵ
- Scale calibrated to median π_nn = 0.4 per (σ, c) cell
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
import json
import geopandas as gpd

from calibrate import (
    prepare_distances, calibrate_scale_by_pi_nn, invert_model,
    TARGET_MEDIAN_PI_NN,
)

# Load data
admin = gpd.read_file("data/processed/tanzania_calibrated.gpkg")
tc_base_orig = np.load("data/processed/tanzania_trade_costs_baseline.npy")
tc_cf = np.load("data/processed/tanzania_trade_costs_counterfactual.npy")

with open("data/processed/tanzania_model_params.json") as f:
    params = json.load(f)

alpha = params["parameters"]["alpha"]
kappa = params["parameters"]["kappa"]
n_full = len(admin)

L_full = admin["population"].values
Y_full = admin["gdp_usd"].values

# Filter districts (same as run_country.py phase4)
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
print(f"Running sensitivity grid: σ × c (re-inverting per σ)\n")

# Parameter grids
sigmas = [3, 4, 5, 6, 7]
c_ratios = [2.0, 2.5, 3.0, 3.5, 4.0]
C_BASE = 3.0   # the c at which tc_base_orig was constructed

results = np.zeros((len(c_ratios), len(sigmas)))

for ci, c_new in enumerate(c_ratios):
    for si, sigma in enumerate(sigmas):
        # 1. Rebuild baseline trade-cost matrix at new c.
        # tc_b_orig has unpaved roads scaled by c=3; tc_c has all roads at c=1.
        # Rescale: tc_b(c) = tc_c + (tc_b_orig - tc_c) × c/3
        tc_b = tc_c + (tc_b_orig - tc_c) * (c_new / C_BASE)

        # 2. Prepare distances (handle inf, fill diagonal).
        distances = prepare_distances(tc_b)

        # 3. Calibrate scale to median π_nn = 0.4 with this σ.
        try:
            scale, status = calibrate_scale_by_pi_nn(
                L=L, Y=Y, distances=distances,
                sigma=sigma, alpha=alpha, target=TARGET_MEDIAN_PI_NN,
            )
        except Exception as e:
            print(f"  σ={sigma}, c={c_new}: scale-calibration failed: {e}")
            results[ci, si] = np.nan
            continue

        tau = 1.0 + distances / scale
        np.fill_diagonal(tau, 1.0)

        # 4. Re-invert calibration with this σ.
        try:
            A, a, P, pi = invert_model(L, Y, tau, sigma=sigma, kappa=kappa,
                                       alpha=alpha, max_iter=2000, tol=1e-3)
        except Exception as e:
            print(f"  σ={sigma}, c={c_new}: inversion failed: {e}")
            results[ci, si] = np.nan
            continue

        pi_nn = np.diag(pi)

        # 5. Compute d_hat with iceberg-ratio formula (Bug 1 fix).
        # We've rebuilt tc_b at this c, but the disconnected-pair fill happened
        # inside `prepare_distances` for the calibration scale. For d_hat we use
        # the original tc_b/tc_c (with inf, where applicable) and apply the
        # same scale.
        conn = (np.isfinite(tc_b) & np.isfinite(tc_c) & (tc_b > 0) & (tc_c > 0))
        np.fill_diagonal(conn, True)
        d_hat = np.ones((nn, nn))
        mask = conn & ~np.eye(nn, dtype=bool)
        d_hat[mask] = (1.0 + tc_c[mask] / scale) / (1.0 + tc_b[mask] / scale)

        # 6. Stage 1 (fixed population) solver.
        w_hat = np.ones(nn)
        for it in range(3000):
            w_hat_old = w_hat.copy()
            factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma)
            num_cf = pi * factor
            pi_p = num_cf / num_cf.sum(axis=1, keepdims=True)
            rhs = pi_p.T @ (w_hat * wl)
            w_hat_new = rhs / np.maximum(wl, 1e-300)
            w_hat = w_hat**0.7 * np.maximum(w_hat_new, 1e-20)**0.3
            w_hat = w_hat / np.average(w_hat, weights=wl)
            if np.max(np.abs(np.log(w_hat) - np.log(w_hat_old))) < 1e-6:
                break

        # 7. Stage 1 welfare (Bug 5 fix: no leading ŵ).
        pi_nn_p = np.diag(pi_p)
        exp1 = alpha / (sigma - 1)
        welfare_loc = (pi_nn / np.maximum(pi_nn_p, 1e-20))**exp1
        welfare = float(np.average(welfare_loc, weights=L))
        welf_pct = 100 * (welfare - 1)
        results[ci, si] = welf_pct

        print(f"  σ={sigma}, c={c_new}: welfare = {welf_pct:+.1f}%  (scale={scale:.0f}km, status={status})")

# Print table
print(f"\n{'='*70}")
print(f"WELFARE SENSITIVITY TABLE (Stage 1, fixed population) — v2")
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
    f.write("Welfare Sensitivity to sigma and c (Stage 1, fixed population) — v2\n")
    f.write(f"Country: Tanzania, n={nn} districts, alpha={alpha}, kappa={kappa}\n")
    f.write(f"Calibration version: v2-rrh-krugman-cse-row\n")
    f.write(f"Each cell is fully re-calibrated (scale fit to median pi_nn=0.4) per (sigma, c).\n")
    f.write("=" * 60 + "\n")
    f.write(header + "\n")
    f.write("-" * len(header) + "\n")
    for ci, c in enumerate(c_ratios):
        row = f"{c:>8.1f}" + "".join(f"{results[ci,si]:>+10.1f}%" for si in range(len(sigmas)))
        f.write(row + "\n")

print(f"\nSaved to outputs/welfare_sensitivity_sigma_c.txt")
