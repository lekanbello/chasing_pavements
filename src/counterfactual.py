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


def compute_d_hat(tc_base, tc_cf, scale):
    """
    Compute the iceberg-cost ratio d_hat = τ'_ni / τ_ni for hat algebra.

    With τ = 1 + distance / scale, the correct ratio is
        d_hat = (1 + tc_cf / scale) / (1 + tc_base / scale)
    NOT the raw distance ratio (which was the bug in v1).

    For disconnected pairs (inf in either matrix), d_hat = 1 (no change).
    Diagonal d_hat = 1 by definition.
    """
    n = tc_base.shape[0]
    connected = (np.isfinite(tc_base) & np.isfinite(tc_cf) &
                 (tc_base > 0) & (tc_cf > 0))
    np.fill_diagonal(connected, True)

    d_hat = np.ones((n, n))
    mask = connected & ~np.eye(n, dtype=bool)
    d_hat[mask] = (1.0 + tc_cf[mask] / scale) / (1.0 + tc_base[mask] / scale)
    np.fill_diagonal(d_hat, 1.0)

    # Report
    reduced = d_hat[mask & (d_hat < 0.999)]
    if len(reduced) > 0:
        print(f"  d_hat: {len(reduced)} pairs reduced, "
              f"mean={np.mean(reduced):.4f} ({100*(1-np.mean(reduced)):.1f}% avg reduction)")
    print(f"  d_hat range: [{d_hat[mask].min():.4f}, {d_hat[mask].max():.4f}]")

    return d_hat


def solve_counterfactual(L, Y, pi, d_hat, sigma, alpha, kappa=None,
                         max_iter=10000, tol=1e-8):
    """
    Solve counterfactual equilibrium using exact hat algebra (R&RH 2017 Eqs 18-21).

    Three mobility regimes are computed:
      • Stage 1 (κ = 0): no labor mobility. Welfare varies fully across locations.
      • Stage 2 (κ → ∞): perfect mobility. Welfare equalizes across locations.
      • Stage 3 (finite κ): frictional mobility. Welfare varies, but in-migration
        partially equalizes gains. Only computed if `kappa` is provided.

    Stage 2 is the headline. Stage 3 is the principled extension (R&RH 2017 with
    finite migration elasticity).

    Inputs:
        L: population vector (n,)
        Y: GDP vector (n,)
        pi: row-stochastic trade-share matrix (n, n).
            π[n, i] = destination n's expenditure share on origin i.
            Rows sum to 1. (Krugman-CES, R&RH 2017 Eq 9.)
        d_hat: iceberg trade cost ratio τ'/τ (n, n) — destination on row, origin on col.
        sigma: CES elasticity of substitution
        alpha: goods share in utility (1-alpha = housing/land share)
        kappa: migration elasticity for Stage 3. If None, Stage 3 is skipped.

    Outputs:
        dict with welfare changes (Stage 1, 2, 3), CVs, location-by-location welfares,
        wage / population hats, etc.
    """
    n = len(L)
    print(f"\nSolving counterfactual (R&RH 2017)...")
    print(f"  n={n}, σ={sigma}, α={alpha}")
    print(f"  σ(1-α) = {sigma*(1-alpha):.2f} (>1 required: "
          f"{'YES' if sigma*(1-alpha)>1 else 'NO'})")

    w = Y / L
    lam = L / L.sum()
    pi_nn = np.diag(pi)

    # Sanity check: π should be row-stochastic
    row_sum_err = float(np.max(np.abs(pi.sum(axis=1) - 1.0)))
    if row_sum_err > 1e-3:
        print(f"  WARNING: π is not row-stochastic (max row-sum deviation = {row_sum_err:.2e}). "
              f"Did calibration produce row-stochastic π?")

    print(f"  Baseline π_nn: min={pi_nn.min():.4f}, "
          f"median={np.median(pi_nn):.4f}, max={pi_nn.max():.4f}")

    wl = w * lam
    gamma = alpha / (sigma * (1 - alpha) - 1)
    print(f"  γ = {gamma:.4f}")

    # ════════════════════════════════════════════════════════════════
    # Stage 1: Fixed population (L̂ = 1)
    # ════════════════════════════════════════════════════════════════
    print("  Stage 1: Fixed population (no mobility)...")
    w_hat = np.ones(n)
    lam_hat = np.ones(n)
    s1_iter_converged = False
    s1_iter_diff = None
    s1_iter_count = 0

    for iteration in range(max_iter):
        w_hat_old = w_hat.copy()

        # Eq 19 with L̂ = 1: π'_ni = π_ni × (d̂_ni × ŵ_i)^{1-σ} / Σ_k π_nk × (...)
        factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma)
        numerator = pi * factor
        denom = numerator.sum(axis=1, keepdims=True)
        denom = np.maximum(denom, 1e-300)
        pi_prime = numerator / denom

        # Eq 18 wage market clearing (with λ̂ = 1)
        rhs = pi_prime.T @ (w_hat * wl)
        w_hat_new = rhs / np.maximum(wl, 1e-300)

        dampen = 0.3
        w_hat = w_hat**(1 - dampen) * np.maximum(w_hat_new, 1e-20)**dampen
        w_hat = w_hat / np.average(w_hat, weights=wl)

        diff = np.max(np.abs(np.log(w_hat) - np.log(w_hat_old)))
        s1_iter_count = iteration + 1
        s1_iter_diff = float(diff)
        if iteration % 500 == 0:
            print(f"    Iter {iteration}: |Δlogŵ|={diff:.2e}")
        if diff < tol:
            print(f"  Stage 1 converged at iteration {iteration}")
            s1_iter_converged = True
            break
    else:
        print(f"  Stage 1 stopped at {max_iter} (diff={diff:.2e})")

    # Stage 1 welfare (Bug 5 fix — no leading ŵ; ŵ cancels in P̂ under L̂=1)
    factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma)
    numerator = pi * factor
    pi_prime_fixed = numerator / numerator.sum(axis=1, keepdims=True)
    pi_nn_prime_fixed = np.diag(pi_prime_fixed)
    exp1 = alpha / (sigma - 1)
    welfare_fixed = (pi_nn / np.maximum(pi_nn_prime_fixed, 1e-20))**exp1
    welfare_fixed_agg = float(np.average(welfare_fixed, weights=L))
    print(f"  Stage 1 welfare (fixed pop): {100*(welfare_fixed_agg-1):+.2f}%")

    # ════════════════════════════════════════════════════════════════
    # Stage 2: With population mobility
    # ════════════════════════════════════════════════════════════════
    print("\n  Stage 2: Adding population mobility...")
    s2_iter_converged = False
    s2_iter_diff = None
    s2_iter_count = 0

    for iteration in range(max_iter):
        w_hat_old = w_hat.copy()
        lam_hat_old = lam_hat.copy()
        L_hat = lam_hat

        factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma) * L_hat[np.newaxis, :]
        numerator = pi * factor
        denom = numerator.sum(axis=1, keepdims=True)
        denom = np.maximum(denom, 1e-300)
        pi_prime = numerator / denom

        pi_nn_prime = np.diag(pi_prime)
        pi_nn_hat = pi_nn_prime / np.maximum(pi_nn, 1e-300)

        # Eq 20: population mobility
        pi_nn_hat_safe = np.clip(pi_nn_hat, 1e-10, 1e10)
        pi_nn_hat_exp = pi_nn_hat_safe**(-gamma)
        lam_hat_new = pi_nn_hat_exp / np.sum(pi_nn_hat_exp * lam)

        # Eq 18: wage market clearing
        rhs = pi_prime.T @ (w_hat * lam_hat * wl)
        w_hat_new = rhs / np.maximum(lam_hat * wl, 1e-300)

        dampen = 0.1
        w_hat = w_hat**(1 - dampen) * np.clip(w_hat_new, 0.1, 10.0)**dampen
        lam_hat = lam_hat**(1 - dampen) * np.clip(lam_hat_new, 0.1, 10.0)**dampen
        w_hat = w_hat / np.average(w_hat, weights=wl)

        diff_w = np.max(np.abs(np.log(w_hat) - np.log(w_hat_old)))
        diff_l = np.max(np.abs(np.log(np.maximum(lam_hat, 1e-20)) -
                                np.log(np.maximum(lam_hat_old, 1e-20))))
        diff = max(diff_w, diff_l)
        s2_iter_count = iteration + 1
        s2_iter_diff = float(diff)

        if iteration % 500 == 0:
            print(f"    Iter {iteration}: |Δlogŵ|={diff_w:.2e}, |Δlogλ̂|={diff_l:.2e}")
        if diff < tol:
            print(f"  Stage 2 converged at iteration {iteration}")
            s2_iter_converged = True
            break
    else:
        print(f"  Stage 2 stopped at {max_iter} (diff={diff:.2e})")

    # ── Final trade shares ──
    L_hat = lam_hat
    factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma) * L_hat[np.newaxis, :]
    numerator = pi * factor
    pi_prime = numerator / numerator.sum(axis=1, keepdims=True)
    pi_nn_prime = np.diag(pi_prime)

    # ── Eq 21 welfare, location by location ──
    # V̂_n = (π_nn / π'_nn)^{α/(σ-1)} × (λ_n / λ'_n)^{(σ(1-α)-1)/(σ-1)}
    exp1 = alpha / (sigma - 1)
    exp2 = (sigma * (1 - alpha) - 1) / (sigma - 1)
    lam_prime = lam_hat * lam
    welfare_by_loc = (pi_nn / np.maximum(pi_nn_prime, 1e-20))**exp1 * \
                     (lam / np.maximum(lam_prime, 1e-20))**exp2

    # Bug 4 fix: use population-weighted mean (consistent utilitarian aggregate)
    L_prime = L * L_hat
    welfare_change = float(np.average(welfare_by_loc, weights=L_prime))
    welfare_pct = 100 * (welfare_change - 1)
    welfare_cv = float(np.std(welfare_by_loc) / np.mean(welfare_by_loc))

    # Output GDP change (nominal, not the headline)
    Y_prime = Y * w_hat * L_hat
    gdp_pct = 100 * (Y_prime.sum() / Y.sum() - 1)

    print(f"\n  Stage 2 welfare (perfect mobility, pop-weighted mean): {welfare_pct:+.2f}%")
    print(f"  Stage 2 CV across locs:                                {welfare_cv:.4f} (≈0 under perfect mobility)")
    print(f"  GDP change (nominal):                                  {gdp_pct:+.2f}%")
    print(f"  π_nn change: {np.median(pi_nn):.3f} → {np.median(pi_nn_prime):.3f}")

    # Snapshot Stage 2 before Stage 3 overwrites w_hat / lam_hat
    w_hat_s2 = w_hat.copy()
    lam_hat_s2 = lam_hat.copy()
    pi_nn_prime_s2 = pi_nn_prime.copy()
    Y_prime_s2 = Y_prime.copy()
    L_prime_s2 = L_prime.copy()
    welfare_s2_loc = welfare_by_loc.copy()
    welfare_s2_pct = welfare_pct
    welfare_s2_cv = welfare_cv

    # ════════════════════════════════════════════════════════════════
    # Stage 3: Finite-κ frictional mobility (R&RH 2017 with finite migration elasticity)
    #
    # Migration condition: λ̂_n = V̂_n^κ / Σ_k λ_k V̂_k^κ
    # As κ → ∞ this collapses to Stage 2 (welfare equalizes).
    # As κ → 0 this collapses to Stage 1 (no movement).
    # Finite κ gives heterogeneous welfare partially equalized by population shifts.
    #
    # Starting from Stage 2's wages & population hats; iterate to a new fixed point.
    # ════════════════════════════════════════════════════════════════
    welfare_s3_loc = None
    welfare_s3_pct = None
    welfare_s3_cv = None
    w_hat_s3 = None
    lam_hat_s3 = None
    pi_nn_prime_s3 = None
    s3_iter_converged = False
    s3_iter_diff = None
    s3_iter_count = 0
    if kappa is not None:
        print(f"\n  Stage 3: Frictional mobility (κ={kappa})...")

        for iteration in range(max_iter):
            w_hat_old = w_hat.copy()
            lam_hat_old = lam_hat.copy()
            L_hat = lam_hat

            # Trade shares (same form as Stage 2)
            factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma) * L_hat[np.newaxis, :]
            numerator = pi * factor
            denom = numerator.sum(axis=1, keepdims=True)
            denom = np.maximum(denom, 1e-300)
            pi_prime = numerator / denom
            pi_nn_prime = np.diag(pi_prime)

            # Welfare per location (Eq 21)
            lam_p = lam_hat * lam
            V_loc = (pi_nn / np.maximum(pi_nn_prime, 1e-20))**exp1 * \
                    (lam / np.maximum(lam_p, 1e-20))**exp2

            # Migration: λ̂_n ∝ V̂_n^κ, normalized so Σ λ_n × λ̂_n = 1
            V_loc_safe = np.clip(V_loc, 1e-10, 1e10)
            V_kappa = V_loc_safe**kappa
            norm = np.sum(lam * V_kappa)
            lam_hat_new = V_kappa / np.maximum(norm, 1e-300)

            # Wage clearing (same as Stage 2)
            rhs = pi_prime.T @ (w_hat * lam_hat * wl)
            w_hat_new = rhs / np.maximum(lam_hat * wl, 1e-300)

            # Damp (same as Stage 2)
            dampen = 0.1
            w_hat = w_hat**(1 - dampen) * np.clip(w_hat_new, 0.1, 10.0)**dampen
            lam_hat = lam_hat**(1 - dampen) * np.clip(lam_hat_new, 0.1, 10.0)**dampen
            w_hat = w_hat / np.average(w_hat, weights=wl)

            diff_w = np.max(np.abs(np.log(w_hat) - np.log(w_hat_old)))
            diff_l = np.max(np.abs(np.log(np.maximum(lam_hat, 1e-20)) -
                                    np.log(np.maximum(lam_hat_old, 1e-20))))
            diff_iter = max(diff_w, diff_l)
            s3_iter_count = iteration + 1
            s3_iter_diff = float(diff_iter)

            if iteration % 500 == 0:
                print(f"    Iter {iteration}: |Δlogŵ|={diff_w:.2e}, |Δlogλ̂|={diff_l:.2e}")
            if diff_iter < tol:
                print(f"  Stage 3 converged at iteration {iteration}")
                s3_iter_converged = True
                break
        else:
            print(f"  Stage 3 stopped at {max_iter} (diff={diff_iter:.2e})")

        # Final Stage 3 outputs
        w_hat_s3 = w_hat.copy()
        lam_hat_s3 = lam_hat.copy()
        factor = (d_hat * w_hat[np.newaxis, :])**(1 - sigma) * lam_hat[np.newaxis, :]
        numerator = pi * factor
        pi_prime = numerator / np.maximum(numerator.sum(axis=1, keepdims=True), 1e-300)
        pi_nn_prime_s3 = np.diag(pi_prime)
        lam_p_s3 = lam_hat * lam
        welfare_s3_loc = (pi_nn / np.maximum(pi_nn_prime_s3, 1e-20))**exp1 * \
                         (lam / np.maximum(lam_p_s3, 1e-20))**exp2
        L_prime_s3 = L * lam_hat
        welfare_s3_change = float(np.average(welfare_s3_loc, weights=L_prime_s3))
        welfare_s3_pct = 100 * (welfare_s3_change - 1)
        welfare_s3_cv = float(np.std(welfare_s3_loc) / np.mean(welfare_s3_loc))
        print(f"  Stage 3 welfare (κ={kappa}, pop-weighted mean): {welfare_s3_pct:+.2f}%")
        print(f"  Stage 3 CV across locs:                          {welfare_s3_cv:.4f} (>0: heterogeneous)")
        print(f"  Stage 3 welfare range: [{100*(welfare_s3_loc.min()-1):+.1f}%, {100*(welfare_s3_loc.max()-1):+.1f}%]")

    return {
        # Stage 2 (perfect mobility, headline)
        "w_hat": w_hat_s2,
        "L_hat": lam_hat_s2,
        "lam_hat": lam_hat_s2,
        "pi_nn": pi_nn,
        "pi_nn_prime": pi_nn_prime_s2,
        # Bug 6 fix: 'welfare_hat' is the location-by-location Eq 21 welfare under Stage 2
        "welfare_hat": welfare_s2_loc,
        "welfare_by_loc": welfare_s2_loc,
        "welfare_change": float(np.average(welfare_s2_loc, weights=L_prime_s2)),
        "welfare_pct": welfare_s2_pct,
        "welfare_cv": welfare_s2_cv,
        # Stage 1 per-location welfare: pre-mobility incidence.
        "welfare_s1_hat": welfare_fixed,
        # Stage 3 (finite-κ frictional mobility)
        "kappa": kappa,
        "welfare_s3_hat": welfare_s3_loc,
        "welfare_s3_pct": welfare_s3_pct,
        "welfare_s3_cv": welfare_s3_cv,
        "w_hat_s3": w_hat_s3,
        "lam_hat_s3": lam_hat_s3,
        "pi_nn_prime_s3": pi_nn_prime_s3,
        # Solver convergence diagnostics (per stage). Distinct from welfare_cv,
        # which measures cross-locational equalization. iter_converged tracks
        # whether the fixed-point iteration met its tolerance before max_iter.
        "s1_iter_converged": s1_iter_converged,
        "s1_iter_diff": s1_iter_diff,
        "s1_iter_count": s1_iter_count,
        "s2_iter_converged": s2_iter_converged,
        "s2_iter_diff": s2_iter_diff,
        "s2_iter_count": s2_iter_count,
        "s3_iter_converged": s3_iter_converged,
        "s3_iter_diff": s3_iter_diff,
        "s3_iter_count": s3_iter_count,
        # Other
        "gdp_pct": gdp_pct,
        "L_prime": L_prime_s2,
        "Y_prime": Y_prime_s2,
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
    kappa = params["parameters"].get("kappa")    # Stage 3 migration elasticity
    scale = params["trade_cost_scale"]    # needed for τ-ratio d_hat (Bug 1 fix)

    # Sanity: the calibration should be the row-stochastic Krugman-CES version.
    cal_ver = params.get("calibration_version", "v1-legacy")
    if cal_ver != "v2-rrh-krugman-cse-row":
        print(f"  WARNING: calibration_version={cal_ver}; expected v2-rrh-krugman-cse-row.")
        print(f"  Re-run Phase 3 calibration before trusting Phase 4 results.")

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

    # Renormalize rows after subsetting (small renormalization for the kept indices;
    # π is already row-stochastic by construction in v2 calibration).
    row_sums = pi.sum(axis=1, keepdims=True)
    pi = pi / np.maximum(row_sums, 1e-300)

    # ── Compute d_hat (Bug 1 fix: pass scale, use τ-ratio) ──
    d_hat = compute_d_hat(tc_base_sub, tc_cf_sub, scale)

    # ── Solve (Stage 1 + Stage 2 perfect mobility + Stage 3 finite-κ) ──
    results = solve_counterfactual(L, Y, pi, d_hat, sigma, alpha, kappa=kappa)

    # ── Print ──
    print("\n" + "=" * 70)
    print("COUNTERFACTUAL: PAVE ALL ROADS IN TANZANIA")
    print("=" * 70)
    print(f"\n  ┌───────────────────────────────────────────────┐")
    print(f"  │  Welfare gain from full paving:  {results['welfare_pct']:>+6.2f}%       │")
    print(f"  │  GDP change:                     {results['gdp_pct']:>+6.2f}%       │")
    print(f"  └───────────────────────────────────────────────┘")

    welfare_hat = results["welfare_hat"]
    L_hat = results["L_hat"]
    welfare_pct_loc = 100 * (welfare_hat - 1)

    print(f"\n  Top 10 Winners (by Eq 21 welfare gain):")
    for rank, i in enumerate(np.argsort(welfare_pct_loc)[::-1][:10]):
        name = admin_sub.iloc[i]["NAME_2"]
        region = admin_sub.iloc[i]["NAME_1"]
        print(f"    {rank+1:2d}. {name:20s} ({region:15s})  "
              f"welfare: {welfare_pct_loc[i]:>+6.1f}%  pop: {100*(L_hat[i]-1):>+6.1f}%")

    print(f"\n  Top 10 Losers:")
    for rank, i in enumerate(np.argsort(welfare_pct_loc)[:10]):
        name = admin_sub.iloc[i]["NAME_2"]
        region = admin_sub.iloc[i]["NAME_1"]
        print(f"    {rank+1:2d}. {name:20s} ({region:15s})  "
              f"welfare: {welfare_pct_loc[i]:>+6.1f}%  pop: {100*(L_hat[i]-1):>+6.1f}%")

    print(f"\n  Distribution of welfare changes (Eq 21):")
    print(f"    Pop-weighted mean: {results['welfare_pct']:>+6.2f}%  (headline)")
    print(f"    Median:            {np.median(welfare_pct_loc):>+6.2f}%")
    print(f"    Std:               {np.std(welfare_pct_loc):>6.2f}%")
    print(f"    Range:             [{welfare_pct_loc.min():>+.1f}%, {welfare_pct_loc.max():>+.1f}%]")
    print(f"    Gaining:           {(welfare_pct_loc > 0).sum()} / {n}")
    print(f"    Losing:            {(welfare_pct_loc < 0).sum()} / {n}")

    # ── Save ──
    print("\nSaving...")
    admin_out = admin_sub.copy()
    admin_out["wage_hat"] = results["w_hat"]
    admin_out["pop_hat"] = results["L_hat"]
    # Bug 6 fix: 'welfare_hat' replaces v1's 'real_income_hat'.
    # Map and headline now compute the same Eq 21 object.
    admin_out["welfare_hat"] = welfare_hat
    admin_out["welfare_pct"] = welfare_pct_loc
    # Stage 1 (pre-mobility) per-location welfare — the right object for "winners and losers" maps.
    admin_out["welfare_s1_hat"] = results["welfare_s1_hat"]
    admin_out["welfare_s1_pct"] = 100 * (results["welfare_s1_hat"] - 1)
    # Stage 3 (finite-κ frictional mobility) per-location welfare and population.
    if results.get("welfare_s3_hat") is not None:
        admin_out["welfare_s3_hat"] = results["welfare_s3_hat"]
        admin_out["welfare_s3_pct"] = 100 * (results["welfare_s3_hat"] - 1)
        admin_out["pop_s3_hat"] = results["lam_hat_s3"]
        admin_out["pop_s3_pct"] = 100 * (results["lam_hat_s3"] - 1)
    admin_out["pop_pct"] = 100 * (results["L_hat"] - 1)
    admin_out["gdp_prime"] = results["Y_prime"]
    admin_out.to_file(OUTPUT_DISTRICT, driver="GPKG")

    agg = {
        "counterfactual": "pave_all_roads",
        "country": "Tanzania",
        "year": params["year"],
        "parameters": params["parameters"],
        "calibration_version": cal_ver,
        "n_districts": n,
        # Stage 2 (perfect mobility, headline)
        "welfare_pct": float(results["welfare_pct"]),
        "welfare_cv": float(results["welfare_cv"]),
        # Stage 3 (frictional mobility)
        "welfare_s3_pct": (float(results["welfare_s3_pct"])
                           if results.get("welfare_s3_pct") is not None else None),
        "welfare_s3_cv": (float(results["welfare_s3_cv"])
                          if results.get("welfare_s3_cv") is not None else None),
        "kappa": results.get("kappa"),
        # Solver-level convergence diagnostics (distinct from welfare_cv).
        # iter_converged = fixed-point iteration met tolerance; iter_diff = final residual.
        "s1_iter_converged": bool(results.get("s1_iter_converged", False)),
        "s1_iter_diff": results.get("s1_iter_diff"),
        "s2_iter_converged": bool(results.get("s2_iter_converged", False)),
        "s2_iter_diff": results.get("s2_iter_diff"),
        "s3_iter_converged": bool(results.get("s3_iter_converged", False)),
        "s3_iter_diff": results.get("s3_iter_diff"),
        # Welfare equalization diagnostic (was named stage2_converged in v2.0;
        # renamed because welfare equalization ≠ solver convergence).
        "welfare_equalized": bool(results["welfare_cv"] < 0.05),
        "gdp_pct": float(results["gdp_pct"]),
    }
    with open(OUTPUT_RESULTS, "w") as f:
        json.dump(agg, f, indent=2)

    print(f"  {OUTPUT_DISTRICT}")
    print(f"  {OUTPUT_RESULTS}")
    print("=" * 70)


if __name__ == "__main__":
    main()
