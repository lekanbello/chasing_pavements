"""
counterfactual.py — Phase 4: Counterfactual equilibrium and welfare gains.

Implements the exact hat algebra from Redding & Rossi-Hansberg (2017),
Equations 18-21. Takes baseline trade shares from calibration and
trade cost ratios (d_hat = counterfactual/baseline) from the road network.

Key insight: the hat algebra only needs trade cost RATIOS, not levels.
d_hat = weighted_km_cf / weighted_km_baseline, range [0.33, 1.0].
No normalization or overflow issues.
"""

import os
import json
import numpy as np
import geopandas as gpd

# ── Configuration ──────────────────────────────────────────────────────

CALIBRATED_PATH = "data/processed/tanzania_calibrated.gpkg"
BASELINE_TC_PATH = "data/processed/tanzania_trade_costs_baseline.npy"
COUNTERFACTUAL_TC_PATH = "data/processed/tanzania_trade_costs_counterfactual.npy"
TRADE_SHARES_PATH = "data/processed/tanzania_baseline_trade_shares.npy"
PARAMS_PATH = "data/processed/tanzania_model_params.json"

OUTPUT_DIR = "data/processed"
OUTPUT_RESULTS = os.path.join(OUTPUT_DIR, "tanzania_counterfactual_results.json")
OUTPUT_DISTRICT = os.path.join(OUTPUT_DIR, "tanzania_counterfactual.gpkg")


def compute_d_hat(tc_base, tc_cf):
    """
    Compute trade cost changes d_hat = d'_ni / d_ni.

    Since both baseline and counterfactual use the same iceberg formula
    (tau = 1 + distance/scale), the ratio simplifies to:
        d_hat = (1 + dist_cf/scale) / (1 + dist_base/scale)
    which equals dist_cf / dist_base for large distances.

    For disconnected pairs (inf in either matrix), d_hat = 1 (no change).
    """
    n = tc_base.shape[0]
    connected = (np.isfinite(tc_base) & np.isfinite(tc_cf) &
                 (tc_base > 0) & (tc_cf > 0))
    np.fill_diagonal(connected, True)

    d_hat = np.ones((n, n))
    mask = connected & ~np.eye(n, dtype=bool)
    d_hat[mask] = tc_cf[mask] / tc_base[mask]
    np.fill_diagonal(d_hat, 1.0)

    # Report
    reduced = d_hat[mask & (d_hat < 0.999)]
    if len(reduced) > 0:
        print(f"  d_hat: {len(reduced)} pairs reduced, "
              f"mean={np.mean(reduced):.4f} ({100*(1-np.mean(reduced)):.1f}% avg reduction)")
    print(f"  d_hat range: [{d_hat[mask].min():.4f}, {d_hat[mask].max():.4f}]")

    return d_hat


def solve_counterfactual(L, Y, pi, d_hat, sigma, alpha,
                         max_iter=10000, tol=1e-8):
    """
    Solve counterfactual equilibrium using exact hat algebra.

    Following Redding & Rossi-Hansberg (2017), Equations 18-21.

    Inputs:
        L: population vector (n,)
        Y: GDP vector (n,)
        pi: baseline trade share matrix (n, n) — π_ni = share of n's
            expenditure on goods from i
        d_hat: trade cost changes (n, n) — d'_ni / d_ni
        sigma: elasticity of substitution
        alpha: goods share in utility (1-alpha = land share)

    Outputs:
        dict with welfare change, wage changes, population changes, etc.
    """
    n = len(L)
    print(f"\nSolving counterfactual (Redding & Rossi-Hansberg 2017)...")
    print(f"  n={n}, σ={sigma}, α={alpha}")
    print(f"  σ(1-α) = {sigma*(1-alpha):.2f} (>1 required: "
          f"{'YES' if sigma*(1-alpha)>1 else 'NO'})")

    w = Y / L
    lam = L / L.sum()
    pi_nn = np.diag(pi)

    print(f"  Baseline π_nn: min={pi_nn.min():.4f}, "
          f"median={np.median(pi_nn):.4f}, max={pi_nn.max():.4f}")

    # Income shares (baseline)
    wl = w * lam

    # Key exponent for population mobility (Eq 20)
    gamma = alpha / (sigma * (1 - alpha) - 1)
    print(f"  γ = {gamma:.4f}")

    # ════════════════════════════════════════════════════════════════
    # Stage 1: Solve for wages with FIXED population (no mobility)
    # This is numerically stable and gives us a good starting point
    # ════════════════════════════════════════════════════════════════
    print("  Stage 1: Fixed population (no mobility)...")
    w_hat = np.ones(n)
    lam_hat = np.ones(n)
    L_hat = np.ones(n)

    for iteration in range(max_iter):
        w_hat_old = w_hat.copy()

        # Eq 19: trade shares (with L_hat fixed at 1)
        factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma)
        numerator = pi * factor
        denom = numerator.sum(axis=1, keepdims=True)
        denom = np.maximum(denom, 1e-300)
        pi_prime = numerator / denom

        # Eq 18: market clearing (with λ̂=1)
        rhs = pi_prime.T @ (w_hat * wl)
        w_hat_new = rhs / np.maximum(wl, 1e-300)

        # Dampened update
        dampen = 0.3
        w_hat = w_hat**(1 - dampen) * np.maximum(w_hat_new, 1e-20)**dampen
        w_hat = w_hat / np.average(w_hat, weights=wl)

        diff = np.max(np.abs(np.log(w_hat) - np.log(w_hat_old)))
        if iteration % 500 == 0:
            print(f"    Iter {iteration}: |Δlogŵ|={diff:.2e}")
        if diff < tol:
            print(f"  Stage 1 converged at iteration {iteration}")
            break
    else:
        print(f"  Stage 1 stopped at {max_iter} (diff={diff:.2e})")

    # Compute Stage 1 welfare (no mobility = direct trade cost effect only)
    factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma)
    numerator = pi * factor
    pi_prime_fixed = numerator / numerator.sum(axis=1, keepdims=True)
    pi_nn_prime_fixed = np.diag(pi_prime_fixed)

    # Welfare without mobility: just the price index effect
    # V̂ = ŵ × (Σ_i π_ni (d̂_ni ŵ_i)^{1-σ})^{1/(σ-1)} ... simplifies to
    # For fixed pop: V̂_n = ŵ_n × (π_nn / π'_nn)^{α/(σ-1)}
    exp1 = alpha / (sigma - 1)
    welfare_fixed = w_hat * (pi_nn / np.maximum(pi_nn_prime_fixed, 1e-20))**exp1
    welfare_fixed_agg = np.average(welfare_fixed, weights=L)
    print(f"  Stage 1 welfare (fixed pop): {100*(welfare_fixed_agg-1):+.2f}%")

    # ════════════════════════════════════════════════════════════════
    # Stage 2: Add population mobility
    # Starting from Stage 1 wages, iterate on both w and λ
    # ════════════════════════════════════════════════════════════════
    print("\n  Stage 2: Adding population mobility...")

    for iteration in range(max_iter):
        w_hat_old = w_hat.copy()
        lam_hat_old = lam_hat.copy()
        L_hat = lam_hat

        # Eq 19: trade shares
        factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma) * L_hat[np.newaxis, :]
        numerator = pi * factor
        denom = numerator.sum(axis=1, keepdims=True)
        denom = np.maximum(denom, 1e-300)
        pi_prime = numerator / denom

        pi_nn_prime = np.diag(pi_prime)
        pi_nn_hat = pi_nn_prime / np.maximum(pi_nn, 1e-300)

        # Eq 20: population
        pi_nn_hat_safe = np.clip(pi_nn_hat, 1e-10, 1e10)
        pi_nn_hat_exp = pi_nn_hat_safe**(-gamma)
        lam_hat_new = pi_nn_hat_exp / np.sum(pi_nn_hat_exp * lam)

        # Eq 18: wages
        rhs = pi_prime.T @ (w_hat * lam_hat * wl)
        w_hat_new = rhs / np.maximum(lam_hat * wl, 1e-300)

        # Very conservative dampening for stability
        dampen = 0.1
        w_hat = w_hat**(1 - dampen) * np.clip(w_hat_new, 0.1, 10.0)**dampen
        lam_hat = lam_hat**(1 - dampen) * np.clip(lam_hat_new, 0.1, 10.0)**dampen
        w_hat = w_hat / np.average(w_hat, weights=wl)

        diff_w = np.max(np.abs(np.log(w_hat) - np.log(w_hat_old)))
        diff_l = np.max(np.abs(np.log(np.maximum(lam_hat, 1e-20)) -
                                np.log(np.maximum(lam_hat_old, 1e-20))))
        diff = max(diff_w, diff_l)

        if iteration % 500 == 0:
            print(f"    Iter {iteration}: |Δlogŵ|={diff_w:.2e}, |Δlogλ̂|={diff_l:.2e}")
        if diff < tol:
            print(f"  Stage 2 converged at iteration {iteration}")
            break
    else:
        print(f"  Stage 2 stopped at {max_iter} (diff={diff:.2e})")

    # ── Final trade shares ──
    L_hat = lam_hat
    factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma) * L_hat[np.newaxis, :]
    numerator = pi * factor
    pi_prime = numerator / numerator.sum(axis=1, keepdims=True)
    pi_nn_prime = np.diag(pi_prime)

    # ── Welfare (Eq 21) ──
    # V̄'/V̄ = (π_nn / π'_nn)^{α/(σ-1)} × (λ_n / λ'_n)^{(σ(1-α)-1)/(σ-1)}
    exp1 = alpha / (sigma - 1)
    exp2 = (sigma * (1 - alpha) - 1) / (sigma - 1)

    lam_prime = lam_hat * lam
    welfare_by_loc = (pi_nn / np.maximum(pi_nn_prime, 1e-20))**exp1 * \
                     (lam / np.maximum(lam_prime, 1e-20))**exp2

    # Under perfect mobility, welfare should be equalized
    welfare_cv = np.std(welfare_by_loc) / np.mean(welfare_by_loc)
    welfare_change = np.median(welfare_by_loc)
    welfare_pct = 100 * (welfare_change - 1)

    # GDP change
    Y_prime = Y * w_hat * L_hat
    gdp_pct = 100 * (Y_prime.sum() / Y.sum() - 1)

    # Real income by location (for mapping)
    real_income_hat = w_hat * (pi_nn / np.maximum(pi_nn_prime, 1e-20))**(1.0 / (sigma - 1))

    print(f"\n  Welfare (Eq 21, median):    {welfare_pct:+.2f}%")
    print(f"  Welfare CV across locs:      {welfare_cv:.4f} (should be ~0 under perfect mobility)")
    print(f"  GDP change:                  {gdp_pct:+.2f}%")
    print(f"  π_nn change: {np.median(pi_nn):.3f} → {np.median(pi_nn_prime):.3f}")

    return {
        "w_hat": w_hat,
        "L_hat": L_hat,
        "lam_hat": lam_hat,
        "pi_nn": pi_nn,
        "pi_nn_prime": pi_nn_prime,
        "real_income_hat": real_income_hat,
        "welfare_by_loc": welfare_by_loc,
        "welfare_change": welfare_change,
        "welfare_pct": welfare_pct,
        "welfare_cv": welfare_cv,
        "gdp_pct": gdp_pct,
        "L_prime": L * L_hat,
        "Y_prime": Y_prime,
    }


def main():
    print("Loading calibrated model and trade costs...")
    admin = gpd.read_file(CALIBRATED_PATH)
    tc_base = np.load(BASELINE_TC_PATH)
    tc_cf = np.load(COUNTERFACTUAL_TC_PATH)
    pi_full = np.load(TRADE_SHARES_PATH)

    with open(PARAMS_PATH) as f:
        params = json.load(f)

    n = len(admin)
    sigma = params["parameters"]["sigma"]
    alpha = params["parameters"]["alpha"]

    L = admin["population"].values
    Y = admin["gdp_usd"].values

    # ── Filter districts ──
    MIN_POP = 1000
    keep = np.ones(n, dtype=bool)
    for i in range(n):
        name = admin.iloc[i]["NAME_2"]
        if any(w in name.lower() for w in ["lake ", "mafia"]):
            keep[i] = False
        if L[i] < MIN_POP:
            keep[i] = False
        row = tc_base[i, :]
        finite_conn = np.isfinite(row) & (np.arange(n) != i) & (row > 0)
        if finite_conn.sum() == 0:
            keep[i] = False

    keep_idx = np.where(keep)[0]
    n_kept = len(keep_idx)
    dropped = [admin.iloc[i]["NAME_2"] for i in range(n) if not keep[i]]
    print(f"  Dropped {n - n_kept} districts: {dropped[:10]}{'...' if len(dropped)>10 else ''}")
    print(f"  Keeping {n_kept} districts")

    L = L[keep_idx]
    Y = Y[keep_idx]
    tc_base_sub = tc_base[np.ix_(keep_idx, keep_idx)]
    tc_cf_sub = tc_cf[np.ix_(keep_idx, keep_idx)]
    pi = pi_full[np.ix_(keep_idx, keep_idx)]
    admin_sub = admin.iloc[keep_idx].reset_index(drop=True)
    n = n_kept

    # Renormalize trade shares after subsetting (rows must sum to 1)
    row_sums = pi.sum(axis=1, keepdims=True)
    pi = pi / np.maximum(row_sums, 1e-300)

    # ── Compute d_hat ──
    d_hat = compute_d_hat(tc_base_sub, tc_cf_sub)

    # ── Solve ──
    results = solve_counterfactual(L, Y, pi, d_hat, sigma, alpha)

    # ── Print ──
    print("\n" + "=" * 70)
    print("COUNTERFACTUAL: PAVE ALL ROADS IN TANZANIA")
    print("=" * 70)
    print(f"\n  ┌───────────────────────────────────────────────┐")
    print(f"  │  Welfare gain from full paving:  {results['welfare_pct']:>+6.2f}%       │")
    print(f"  │  GDP change:                     {results['gdp_pct']:>+6.2f}%       │")
    print(f"  └───────────────────────────────────────────────┘")

    real_inc = results["real_income_hat"]
    L_hat = results["L_hat"]
    ri_pct = 100 * (real_inc - 1)

    print(f"\n  Top 10 Winners:")
    for rank, i in enumerate(np.argsort(ri_pct)[::-1][:10]):
        name = admin_sub.iloc[i]["NAME_2"]
        region = admin_sub.iloc[i]["NAME_1"]
        print(f"    {rank+1:2d}. {name:20s} ({region:15s})  "
              f"income: {ri_pct[i]:>+6.1f}%  pop: {100*(L_hat[i]-1):>+6.1f}%")

    print(f"\n  Top 10 Losers:")
    for rank, i in enumerate(np.argsort(ri_pct)[:10]):
        name = admin_sub.iloc[i]["NAME_2"]
        region = admin_sub.iloc[i]["NAME_1"]
        print(f"    {rank+1:2d}. {name:20s} ({region:15s})  "
              f"income: {ri_pct[i]:>+6.1f}%  pop: {100*(L_hat[i]-1):>+6.1f}%")

    print(f"\n  Distribution of real income changes:")
    print(f"    Mean:   {np.mean(ri_pct):>+6.2f}%")
    print(f"    Median: {np.median(ri_pct):>+6.2f}%")
    print(f"    Std:    {np.std(ri_pct):>6.2f}%")
    print(f"    Range:  [{np.min(ri_pct):>+.1f}%, {np.max(ri_pct):>+.1f}%]")
    print(f"    Gaining: {(ri_pct > 0).sum()} / {n}")
    print(f"    Losing:  {(ri_pct < 0).sum()} / {n}")

    # ── Save ──
    print("\nSaving...")
    admin_out = admin_sub.copy()
    admin_out["wage_hat"] = results["w_hat"]
    admin_out["pop_hat"] = results["L_hat"]
    admin_out["real_income_hat"] = results["real_income_hat"]
    admin_out["real_income_pct"] = ri_pct
    admin_out["pop_pct"] = 100 * (results["L_hat"] - 1)
    admin_out["gdp_prime"] = results["Y_prime"]
    admin_out.to_file(OUTPUT_DISTRICT, driver="GPKG")

    agg = {
        "counterfactual": "pave_all_roads",
        "country": "Tanzania",
        "year": params["year"],
        "parameters": params["parameters"],
        "n_districts": n,
        "welfare_pct": float(results["welfare_pct"]),
        "welfare_cv": float(results["welfare_cv"]),
        "gdp_pct": float(results["gdp_pct"]),
    }
    with open(OUTPUT_RESULTS, "w") as f:
        json.dump(agg, f, indent=2)

    print(f"  {OUTPUT_DISTRICT}")
    print(f"  {OUTPUT_RESULTS}")
    print("=" * 70)


if __name__ == "__main__":
    main()
