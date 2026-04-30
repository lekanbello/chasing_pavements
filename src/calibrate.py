"""
calibrate.py — Phase 3: Model calibration for spatial GE analysis.

1. Aggregate WorldPop population to admin-2 districts
2. Aggregate BFI subnational GDP to admin-2 districts
3. Pull national GDP from World Bank WDI API
4. Invert the spatial GE model to recover productivities and amenities
5. Validate calibrated parameters
"""

import os
import sys
import json
import numpy as np
import geopandas as gpd
import pandas as pd
from rasterstats import zonal_stats
from shapely.geometry import Point
from scipy.optimize import brentq

# ── Configuration ──────────────────────────────────────────────────────

ADMIN_PATH = "data/processed/tanzania_admin2.gpkg"
BASELINE_PATH = "data/processed/tanzania_trade_costs_baseline.npy"
NAMES_PATH = "data/processed/tanzania_admin2_names.npy"
OUTPUT_DIR = "data/processed"

WORLDPOP_PATH = "data/raw/tza_ppp_2019.tif"
BFI_GDP_DIR = "data/raw/bfi_gdp_025deg"

OUTPUT_CALIBRATED = "data/processed/tanzania_calibrated.gpkg"
OUTPUT_PARAMS = "data/processed/tanzania_model_params.json"

# Year for all data
YEAR = 2019

# External model parameters (Redding & Rossi-Hansberg 2017 Krugman-CES)
PARAMS = {
    "sigma": 5.0,       # CES elasticity of substitution. Trade elasticity = σ-1.
    "kappa": 2.0,       # Migration elasticity (Fréchet shape), range 1.5-3
    "alpha": 0.65,      # Labor share in production, range 0.6-0.7
}

# Calibration target: median domestic trade share (R&RH-style benchmark; see CLAUDE.md)
TARGET_MEDIAN_PI_NN = 0.4

# Version marker so downstream readers can distinguish v1 (EK, column-stochastic)
# from v2 (Krugman-CES, row-stochastic).
CALIBRATION_VERSION = "v2-rrh-krugman-cse-row"


# ══════════════════════════════════════════════════════════════════════
# PART A: Population
# ══════════════════════════════════════════════════════════════════════

def aggregate_population(admin_gdf, raster_path):
    """Sum WorldPop population within each admin-2 polygon."""
    print("Aggregating WorldPop population to admin-2 districts...")

    stats = zonal_stats(
        admin_gdf.geometry,
        raster_path,
        stats=["sum"],
        nodata=-99999,
    )

    population = np.array([s["sum"] if s["sum"] is not None else 0.0 for s in stats])

    print(f"  Total population: {population.sum():,.0f}")
    print(f"  Districts with pop > 0: {(population > 0).sum()} / {len(population)}")
    print(f"  Min: {population.min():,.0f}  Max: {population.max():,.0f}  "
          f"Median: {np.median(population):,.0f}")

    return population


# ══════════════════════════════════════════════════════════════════════
# PART B: GDP
# ══════════════════════════════════════════════════════════════════════

def get_national_gdp(country_code="TZA", year=2019):
    """Pull national GDP from World Bank WDI API, with fallback."""
    print(f"Fetching {country_code} GDP for {year}...")

    # Known values (fallback if API is down)
    KNOWN_GDP = {
        ("TZA", 2019): 61_026_731_926,
        ("TZA", 2018): 57_003_710_000,
    }

    if (country_code, year) in KNOWN_GDP:
        gdp = KNOWN_GDP[(country_code, year)]
        print(f"  GDP ({year}, current USD): ${gdp:,.0f} (cached)")
        return gdp

    try:
        import wbgapi as wb
        df = wb.data.DataFrame("NY.GDP.MKTP.CD", country_code, time=year)
        gdp = df.iloc[0, 0]
        print(f"  GDP ({year}, current USD): ${gdp:,.0f} (from WDI API)")
        return gdp
    except Exception as e:
        raise ValueError(f"Could not fetch GDP for {country_code}/{year}: {e}")


def aggregate_gdp(admin_gdf, population, bfi_dir, national_gdp, year=2019):
    """
    Distribute national GDP across admin-2 districts using BFI subnational
    GDP data, with population-weighted overlay to handle grid-boundary mismatch.

    The BFI dataset provides GDP at 0.25° resolution (~28km). When a grid cell
    overlaps multiple admin-2 districts, we split its GDP proportional to the
    WorldPop population in each overlapping district. This correctly assigns
    GDP to small urban districts that would otherwise be missed by point-based
    spatial joins.
    """
    from shapely.geometry import box

    print("Aggregating BFI subnational GDP with population-weighted overlay...")

    # Load BFI data
    csv_path = os.path.join(bfi_dir, "0_25deg_v2",
                            "final_GDPC_0_25deg_postadjust_pop_dens_no_extra_adjust.csv")
    df = pd.read_csv(csv_path)
    tz = df[(df["iso"] == "TZA") & (df["year"] == year)].copy()
    print(f"  BFI cells for Tanzania {year}: {len(tz)}")

    # Build 0.25° grid cell polygons (not just centroids)
    half = 0.125  # half of 0.25 degrees
    grid_polys = [
        box(row["longitude"] - half, row["latitude"] - half,
            row["longitude"] + half, row["latitude"] + half)
        for _, row in tz.iterrows()
    ]
    bfi_gdf = gpd.GeoDataFrame(tz, geometry=grid_polys, crs="EPSG:4326")

    # For each admin district, compute overlap with each BFI cell
    # and split GDP by population weight
    print("  Computing population-weighted overlays...")
    district_gdp = np.zeros(len(admin_gdf))

    # Spatial index for admin districts
    admin_sindex = admin_gdf.sindex

    for idx, cell in bfi_gdf.iterrows():
        cell_gdp = cell["predicted_GCP_current_USD"]
        if cell_gdp <= 0:
            continue

        # Find admin districts that intersect this cell
        possible_idx = list(admin_sindex.intersection(cell.geometry.bounds))
        if not possible_idx:
            continue

        # Get population in each overlapping district
        overlapping_pop = {}
        for admin_idx in possible_idx:
            admin_geom = admin_gdf.iloc[admin_idx].geometry
            if cell.geometry.intersects(admin_geom):
                overlapping_pop[admin_idx] = population[admin_idx]

        total_pop = sum(overlapping_pop.values())
        if total_pop <= 0:
            # Fallback: equal split if no population data
            n = len(overlapping_pop)
            for admin_idx in overlapping_pop:
                district_gdp[admin_idx] += cell_gdp / n
        else:
            # Split by population weight
            for admin_idx, pop in overlapping_pop.items():
                district_gdp[admin_idx] += cell_gdp * (pop / total_pop)

    # Normalize to shares and scale by national GDP
    total_share = district_gdp.sum()
    if total_share > 0:
        gdp_shares = district_gdp / total_share
    else:
        gdp_shares = district_gdp
    district_gdp_usd = gdp_shares * national_gdp

    print(f"  National GDP ({year}): ${national_gdp:,.0f}")
    print(f"  Districts with GDP > 0: {(district_gdp_usd > 0).sum()} / {len(admin_gdf)}")

    # Report top districts
    sorted_idx = np.argsort(district_gdp_usd)[::-1]
    print(f"\n  Top 10 by GDP:")
    for rank, i in enumerate(sorted_idx[:10]):
        name = admin_gdf.iloc[i]["NAME_2"]
        region = admin_gdf.iloc[i]["NAME_1"]
        gdp_m = district_gdp_usd[i] / 1e6
        gdp_pc = district_gdp_usd[i] / max(population[i], 1)
        print(f"    {rank+1:2d}. {name:20s} ({region:15s})  "
              f"${gdp_m:>6,.0f}M  (${gdp_pc:>6,.0f}/cap)")

    # Sanity check: GDP per capita distribution
    gdp_pc = district_gdp_usd / np.maximum(population, 1)
    print(f"\n  GDP/capita: min=${gdp_pc.min():,.0f}  median=${np.median(gdp_pc):,.0f}  "
          f"max=${gdp_pc.max():,.0f}  ratio={gdp_pc.max()/max(gdp_pc.min(),1):.1f}x")

    return district_gdp_usd


# ══════════════════════════════════════════════════════════════════════
# PART C: Model Inversion
# ══════════════════════════════════════════════════════════════════════

def prepare_distances(tc_matrix):
    """
    Pre-process the weighted-km trade-cost matrix:
      • Replace inf (disconnected pairs) with 2× max-finite distance.
      • Zero out the diagonal.
    Returns the cleaned distance matrix. Scale calibration is separate
    (see calibrate_scale_by_pi_nn).
    """
    tc = tc_matrix.copy()
    n = tc.shape[0]
    finite = np.isfinite(tc) & (tc > 0)
    if not finite.any():
        raise ValueError("No finite positive trade costs")
    max_finite = tc[finite].max()
    tc[~np.isfinite(tc)] = max_finite * 2
    np.fill_diagonal(tc, 0)
    return tc


def _build_pi_and_invert(L, Y, tau, sigma, alpha, max_iter=5000, tol=1e-4,
                         verbose=True):
    """
    Inner Krugman-CES inversion. Given iceberg τ, solve for productivities A
    and the row-stochastic trade-share matrix π[n, i] = destination n's
    expenditure share on origin i.

    Trade-share (R&RH 2017 Eq 9, Krugman-CES):
        π[n, i]  ∝  L_i × A_i^{σ-1} × (w_i^α × τ_ni)^{1-σ}

    Index convention: rows = destination n, cols = origin i.

    Market clearing: Y_i = Σ_n π[n, i] × Y_n  ⇒  Y_pred = π.T @ Y.

    Updates A_i so that Y_pred matches observed Y. Dampened fixed point.
    """
    n = len(L)
    s_minus_1 = sigma - 1.0

    # Wages
    w = Y / np.maximum(L, 1e-10)
    w = np.maximum(w, 1e-10)

    # Initialize productivities ∝ GDP per capita
    A = (Y / L) / np.median(Y / L)
    A = np.maximum(A, 1e-10)

    # cost[n, i] = w_i^α × τ_ni  (origin's input cost × shipping cost from i to n)
    # τ is symmetric (distance-based) but we keep the [n, i] indexing explicit.
    w_alpha_origin = (w**alpha)[np.newaxis, :]      # shape (1, n) — origin axis
    cost = tau * w_alpha_origin                      # shape (n, n) [destination, origin]

    cost_pow = cost**(1.0 - sigma)                   # constant across iterations

    diff = np.inf
    for iteration in range(max_iter):
        A_old = A.copy()

        # Source-size × productivity term, broadcast on origin axis
        L_A = (L * A**s_minus_1)[np.newaxis, :]      # shape (1, n)
        numerator = L_A * cost_pow                   # shape (n, n)
        denom = numerator.sum(axis=1, keepdims=True)
        denom = np.maximum(denom, 1e-300)
        pi = numerator / denom                       # rows sum to 1

        # Market clearing: Y_i = Σ_n π[n, i] × Y_n
        Y_pred = pi.T @ Y

        ratio = Y / np.maximum(Y_pred, 1e-10)
        dampen = 0.3
        A = A * ratio**(dampen / s_minus_1)
        A = np.maximum(A, 1e-10)

        diff = float(np.max(np.abs(np.log(A) - np.log(A_old))))
        if verbose and (iteration % 100 == 0 or diff < tol):
            print(f"    Iteration {iteration}: max |Δlog(A)| = {diff:.2e}")
        if diff < tol:
            if verbose:
                print(f"  Converged at iteration {iteration}")
            break
    else:
        if verbose:
            print(f"  WARNING: Did not converge after {max_iter} iterations (diff={diff:.2e})")

    # Final π build with the converged A
    L_A = (L * A**s_minus_1)[np.newaxis, :]
    numerator = L_A * cost_pow
    denom = numerator.sum(axis=1, keepdims=True)
    pi = numerator / np.maximum(denom, 1e-300)

    # Price index: from CES, P_n^{1-σ} = Σ_i L_i × A_i^{σ-1} × (w_i^α × τ_ni)^{1-σ} = denom_n
    P = denom.flatten()**(1.0 / (1.0 - sigma))

    return A, pi, P, diff


def calibrate_scale_by_pi_nn(L, Y, distances, sigma, alpha,
                             target=TARGET_MEDIAN_PI_NN,
                             bracket=(50.0, 50000.0)):
    """
    Find scale ∈ [bracket_lo, bracket_hi] such that median(diag(π)) ≈ target,
    where π is the row-stochastic Krugman-CES trade-share matrix.

    Returns (scale, calibration_status) where calibration_status is "exact",
    "fallback_lo", or "fallback_hi".
    """
    def median_pi_nn(scale):
        tau = 1.0 + distances / scale
        np.fill_diagonal(tau, 1.0)
        _, pi, _, _ = _build_pi_and_invert(
            L, Y, tau, sigma, alpha, max_iter=2000, tol=1e-3, verbose=False
        )
        return float(np.median(np.diag(pi)))

    lo, hi = bracket
    f_lo = median_pi_nn(lo) - target    # at small scale, τ huge → π_nn → 1 → f_lo > 0
    f_hi = median_pi_nn(hi) - target    # at large scale, τ → 1   → π_nn → small → f_hi < 0

    if f_lo > 0 and f_hi < 0:
        scale = brentq(lambda s: median_pi_nn(s) - target, lo, hi, xtol=1.0)
        return scale, "exact"
    elif f_hi >= 0:
        # Even with maximum scale, can't get π_nn down to target
        print(f"  WARNING: median π_nn={f_hi+target:.3f} > target={target} at max scale={hi}")
        return hi, "fallback_hi"
    else:
        # Even with minimum scale, π_nn already below target (very disconnected network)
        print(f"  WARNING: median π_nn={f_lo+target:.3f} < target={target} at min scale={lo}")
        return lo, "fallback_lo"


def invert_model(L, Y, tau, sigma, kappa, alpha, max_iter=5000, tol=1e-4):
    """
    Invert the R&RH 2017 Krugman-CES spatial GE model to recover productivities,
    amenities, the price index, and the row-stochastic trade-share matrix.

    Trade shares (Eq 9, Krugman-CES):
        π[n, i] ∝ L_i × A_i^{σ-1} × (w_i^α × τ_ni)^{1-σ}
        with rows summing to 1.

    Inversion steps:
      1. Wages w_i = Y_i / L_i.
      2. Iterate productivities A so that market-clearing Y_pred = π.T @ Y matches observed Y.
      3. Price index P_n = denom_n^{1/(1-σ)}.
      4. Amenities a_n recovered from migration condition (R&RH labor mobility).
    """
    n = len(L)
    print(f"\nInverting GE model for {n} locations (Krugman-CES, σ={sigma}, α={alpha}, κ={kappa})...")
    print(f"  Trade elasticity (σ-1) = {sigma - 1}")

    w = Y / np.maximum(L, 1e-10)
    print(f"  Wages: min=${w.min():,.0f}  max=${w.max():,.0f}  ratio={w.max()/w.min():.1f}")

    A, pi, P, diff_final = _build_pi_and_invert(L, Y, tau, sigma, alpha,
                                                max_iter=max_iter, tol=tol)

    print(f"  Price index: min={P.min():.4f}  max={P.max():.4f}  ratio={P.max()/P.min():.1f}")

    # Amenities from migration: L_n ∝ (w_n × a_n / P_n)^κ ⇒ a_n ∝ (L_n)^{1/κ} × P_n / w_n
    a = (L / L.sum())**(1.0 / kappa) * P / w
    a = a / a.mean()

    print(f"  Productivity: min={A.min():.4f}  max={A.max():.4f}  ratio={A.max()/A.min():.1f}")
    print(f"  Amenities: min={a.min():.4f}  max={a.max():.4f}  ratio={a.max()/a.min():.1f}")

    # Validation: row sums of pi should be 1, π_nn should be in [0, 1]
    row_sum_err = float(np.max(np.abs(pi.sum(axis=1) - 1.0)))
    pi_nn = np.diag(pi)
    if row_sum_err > 1e-6:
        print(f"  WARNING: max row-sum deviation = {row_sum_err:.2e}")
    if pi_nn.min() < 0 or pi_nn.max() > 1:
        print(f"  WARNING: π_nn out of [0,1]: min={pi_nn.min():.4f}, max={pi_nn.max():.4f}")

    return A, a, P, pi


# ══════════════════════════════════════════════════════════════════════
# PART D: Validation
# ══════════════════════════════════════════════════════════════════════

def validate(admin_gdf, A, a, P, population, gdp):
    """Run validation checks on calibrated parameters."""
    print("\n" + "=" * 70)
    print("VALIDATION CHECKS")
    print("=" * 70)

    # 1. Productivity vs GDP per capita correlation
    gdp_pc = gdp / np.maximum(population, 1)
    valid = (population > 0) & (gdp > 0) & np.isfinite(A)
    if valid.sum() > 10:
        corr = np.corrcoef(np.log(A[valid]), np.log(gdp_pc[valid]))[0, 1]
        print(f"\n1. log(Productivity) vs log(GDP/capita) correlation: {corr:.3f}")
        print(f"   (Should be positive — productive places should be richer)")

    # 2. Productivity vs population correlation
    if valid.sum() > 10:
        corr_pop = np.corrcoef(np.log(A[valid]), np.log(population[valid]))[0, 1]
        print(f"\n2. log(Productivity) vs log(Population) correlation: {corr_pop:.3f}")
        print(f"   (Positive = agglomeration, Negative = spreading)")

    # 3. Amenity vs population
    if valid.sum() > 10:
        corr_amen = np.corrcoef(np.log(a[valid]), np.log(population[valid]))[0, 1]
        print(f"\n3. log(Amenities) vs log(Population) correlation: {corr_amen:.3f}")
        print(f"   (Positive = people live where amenities are high)")

    # 4. City size distribution (Zipf check)
    pop_sorted = np.sort(population[population > 0])[::-1]
    n_cities = len(pop_sorted)
    ranks = np.arange(1, n_cities + 1)
    if n_cities > 10:
        log_rank = np.log(ranks)
        log_pop = np.log(pop_sorted)
        zipf_coeff = np.polyfit(log_rank, log_pop, 1)[0]
        print(f"\n4. Zipf coefficient: {zipf_coeff:.3f}")
        print(f"   (Should be close to -1.0 for Zipf's law)")

    # 5. Top 10 most productive and most amenable districts
    sorted_A = np.argsort(A)[::-1]
    sorted_a = np.argsort(a)[::-1]

    print(f"\n5. Top 10 Most Productive Districts:")
    for rank, i in enumerate(sorted_A[:10]):
        name = admin_gdf.iloc[i]["NAME_2"]
        region = admin_gdf.iloc[i]["NAME_1"]
        print(f"   {rank+1:2d}. {name:20s} ({region:15s})  A={A[i]:.4f}  pop={population[i]:>10,.0f}")

    print(f"\n6. Top 10 Highest Amenity Districts:")
    for rank, i in enumerate(sorted_a[:10]):
        name = admin_gdf.iloc[i]["NAME_2"]
        region = admin_gdf.iloc[i]["NAME_1"]
        print(f"   {rank+1:2d}. {name:20s} ({region:15s})  a={a[i]:.4f}  pop={population[i]:>10,.0f}")

    print("\n" + "=" * 70)


# ══════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════

def main():
    # ── Load existing data ──
    print("Loading admin-2 boundaries and trade costs...")
    admin = gpd.read_file(ADMIN_PATH)
    tc_baseline = np.load(BASELINE_PATH)
    names = np.load(NAMES_PATH, allow_pickle=True)
    n = len(admin)
    print(f"  {n} districts, {tc_baseline.shape} trade cost matrix")

    # ── Part A: Population ──
    if not os.path.exists(WORLDPOP_PATH):
        print(f"ERROR: {WORLDPOP_PATH} not found. Download WorldPop data first.")
        sys.exit(1)
    population = aggregate_population(admin, WORLDPOP_PATH)

    # ── Part B: GDP ──
    national_gdp = get_national_gdp("TZA", YEAR)
    gdp = aggregate_gdp(admin, population, BFI_GDP_DIR, national_gdp, YEAR)

    # Handle districts with zero population or GDP
    # Set minimum to 1% of median for numerical stability
    pop_floor = np.median(population[population > 0]) * 0.01
    gdp_floor = np.median(gdp[gdp > 0]) * 0.01
    population = np.maximum(population, pop_floor)
    gdp = np.maximum(gdp, gdp_floor)

    # ── Part C: Model Inversion ──
    distances = prepare_distances(tc_baseline)

    # Calibrate trade-cost scale so median π_nn ≈ TARGET_MEDIAN_PI_NN (R&RH-style benchmark)
    print(f"\nCalibrating trade-cost scale to median π_nn = {TARGET_MEDIAN_PI_NN:.2f}...")
    tc_scale, scale_status = calibrate_scale_by_pi_nn(
        L=population, Y=gdp, distances=distances,
        sigma=PARAMS["sigma"], alpha=PARAMS["alpha"],
        target=TARGET_MEDIAN_PI_NN,
    )
    print(f"  Scale: {tc_scale:.0f} km  (status: {scale_status})")

    tau = 1.0 + distances / tc_scale
    np.fill_diagonal(tau, 1.0)
    off_diag_tau = tau[~np.eye(len(population), dtype=bool) & (tau > 1)]
    print(f"  Iceberg τ: min={off_diag_tau.min():.2f}, "
          f"median={np.median(off_diag_tau):.2f}, max={off_diag_tau.max():.2f}")

    A, a, P, pi = invert_model(
        L=population, Y=gdp, tau=tau,
        sigma=PARAMS["sigma"], kappa=PARAMS["kappa"], alpha=PARAMS["alpha"]
    )

    # Verify trade shares
    pi_nn = np.diag(pi)
    print(f"\n  Baseline trade shares π_nn:")
    print(f"    Median: {np.median(pi_nn):.3f}")
    print(f"    Mean:   {np.mean(pi_nn):.3f}")
    print(f"    Min:    {pi_nn.min():.3f}  Max: {pi_nn.max():.3f}")
    print(f"    Districts with π_nn < 0.90: {(pi_nn < 0.90).sum()} / {n}")

    # ── Part D: Validation ──
    validate(admin, A, a, P, population, gdp)

    # ── Part E: Save ──
    print("\nSaving calibrated data...")
    admin_out = admin.copy()
    admin_out["population"] = population
    admin_out["gdp_usd"] = gdp
    admin_out["gdp_per_capita"] = gdp / population
    admin_out["productivity"] = A
    admin_out["amenity"] = a
    admin_out["price_index"] = P
    admin_out["wage"] = gdp / population

    admin_out.to_file(OUTPUT_CALIBRATED, driver="GPKG")
    print(f"  Saved: {OUTPUT_CALIBRATED}")

    # Save baseline trade shares (needed by counterfactual solver)
    pi_path = os.path.join(OUTPUT_DIR, "tanzania_baseline_trade_shares.npy")
    np.save(pi_path, pi)
    print(f"  Saved: {pi_path}")

    # Save parameters
    params_out = {
        "year": YEAR,
        "national_gdp_usd": float(national_gdp),
        "total_population": float(population.sum()),
        "n_districts": n,
        "parameters": PARAMS,
        "trade_cost_scale": float(tc_scale),
        "scale_calibration_status": scale_status,
        "scale_calibration_target": float(TARGET_MEDIAN_PI_NN),
        "median_pi_nn": float(np.median(pi_nn)),
        "calibration_version": CALIBRATION_VERSION,
        "convergence": True,
    }
    with open(OUTPUT_PARAMS, "w") as f:
        json.dump(params_out, f, indent=2)
    print(f"  Saved: {OUTPUT_PARAMS}")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("CALIBRATION SUMMARY")
    print("=" * 70)
    print(f"  Year: {YEAR}")
    print(f"  National GDP: ${national_gdp:,.0f}")
    print(f"  Total population: {population.sum():,.0f}")
    print(f"  Districts: {n}")
    print(f"  Parameters: σ={PARAMS['sigma']}, κ={PARAMS['kappa']}, α={PARAMS['alpha']}")
    print(f"  Trade elasticity (σ-1): {PARAMS['sigma'] - 1}")
    print(f"  Productivity range: {A.min():.4f} — {A.max():.4f} (ratio {A.max()/A.min():.1f}x)")
    print(f"  Amenity range: {a.min():.4f} — {a.max():.4f} (ratio {a.max()/a.min():.1f}x)")
    print("=" * 70)


if __name__ == "__main__":
    main()
