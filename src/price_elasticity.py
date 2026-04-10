"""
price_elasticity.py — Estimate distance elasticity of trade costs from food price data.

Computes bilateral price gaps across market pairs and regresses on distance
to estimate the distance-to-trade-cost mapping. Used to calibrate the
trade cost normalization parameter (scale).

Usage:
    python3 src/price_elasticity.py --country kenya
    python3 src/price_elasticity.py --country tanzania
    python3 src/price_elasticity.py --country all
"""

import argparse
import numpy as np
import pandas as pd
import geopandas as gpd
from itertools import combinations
import os


def haversine(lat1, lon1, lat2, lon2):
    """Haversine distance in km."""
    R = 6371
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def run_regression(gaps, dists, yms, label):
    """Run price-distance regression with time FE (demeaned)."""
    reg_df = pd.DataFrame({'gap': gaps, 'dist': dists, 'log_dist': np.log(dists), 'ym': yms})
    for col in ['gap', 'dist', 'log_dist']:
        reg_df[col + '_dm'] = reg_df[col] - reg_df.groupby('ym')[col].transform('mean')

    X = reg_df['dist_dm'].values
    y = reg_df['gap_dm'].values
    beta = (X @ y) / (X @ X)
    resid = y - beta * X
    se = np.sqrt(np.sum(resid**2) / (len(resid)-1) / np.sum(X**2))
    t = beta / se
    r2 = 1 - np.sum(resid**2) / np.sum(y**2) if np.sum(y**2) > 0 else 0

    X_log = reg_df['log_dist_dm'].values
    beta_log = (X_log @ y) / (X_log @ X_log)
    resid_log = y - beta_log * X_log
    se_log = np.sqrt(np.sum(resid_log**2) / (len(resid_log)-1) / np.sum(X_log**2))
    r2_log = 1 - np.sum(resid_log**2) / np.sum(y**2) if np.sum(y**2) > 0 else 0

    med_dist = np.median(dists)

    print(f"\n  {label}")
    print(f"  {'─'*50}")
    print(f"  Observations: {len(gaps):,}")
    print(f"  Mean |log(p_i/p_j)|: {gaps.mean():.4f} ({100*gaps.mean():.1f}%)")
    print(f"  Median distance: {med_dist:.0f} km")
    print(f"  Level:   δ = {beta:.8f}/km (SE {se:.8f}, t={t:.1f}), R²={r2:.4f}")
    print(f"  Log-log: δ = {beta_log:.6f} (SE {se_log:.6f}), R²={r2_log:.4f}")
    if beta > 0:
        print(f"  Implied scale (τ=1+dist/scale): {1/beta:.0f} km")
        print(f"  Price gap at median dist: {100*beta*med_dist:.1f}%")

    return {
        'label': label, 'n_obs': len(gaps), 'n_markets': 0,
        'beta_level': beta, 'se_level': se, 't_level': t, 'r2_level': r2,
        'beta_log': beta_log, 'se_log': se_log, 'r2_log': r2_log,
        'mean_gap': gaps.mean(), 'median_dist': med_dist,
        'implied_scale': 1/beta if beta > 0 else np.inf,
    }


def estimate_kenya():
    """Kenya: RTFP dataset, 234 markets."""
    rtfp_path = 'data/raw/rtfp_prices.csv'

    if not os.path.exists(rtfp_path):
        print("  RTFP dataset not found, skipping Kenya")
        return None

    print("Loading Kenya RTFP data...")
    df = pd.read_csv(rtfp_path,
                     usecols=['ISO3', 'mkt_name', 'lat', 'lon', 'year', 'month', 'o_maize_fao'])
    ken = df[df['ISO3'] == 'KEN'].copy()
    ken['ym'] = ken['year'] * 100 + ken['month']

    markets = ken.groupby('mkt_name').agg(lat=('lat', 'first'), lon=('lon', 'first')).reset_index()
    markets = markets.dropna(subset=['lat', 'lon'])
    ken = ken[ken['mkt_name'].isin(set(markets['mkt_name']))]

    mkt_names = markets['mkt_name'].values
    mkt_lats = markets['lat'].values
    mkt_lons = markets['lon'].values
    n_mkts = len(mkt_names)
    print(f"  {n_mkts} markets with coordinates")

    pairs = [(i, j) for i, j in combinations(range(n_mkts), 2)]
    pair_dist = np.array([haversine(mkt_lats[i], mkt_lons[i], mkt_lats[j], mkt_lons[j])
                          for i, j in pairs])
    valid = [(p, d) for p, d in zip(pairs, pair_dist) if d > 1.0]
    pairs = [v[0] for v in valid]
    pair_dist = np.array([v[1] for v in valid])

    pivot = ken.pivot_table(index='mkt_name', columns='ym', values='o_maize_fao')
    pivot = pivot.reindex(mkt_names)

    all_gaps, all_dists, all_ym = [], [], []
    for ym in pivot.columns:
        prices = pivot[ym].values
        ok = ~np.isnan(prices) & (prices > 0)
        if ok.sum() < 10:
            continue
        for idx, (i, j) in enumerate(pairs):
            if ok[i] and ok[j]:
                all_gaps.append(abs(np.log(prices[i]) - np.log(prices[j])))
                all_dists.append(pair_dist[idx])
                all_ym.append(ym)

    result = run_regression(np.array(all_gaps), np.array(all_dists),
                            np.array(all_ym), f"Kenya (RTFP, {n_mkts} markets, maize)")
    result['n_markets'] = n_mkts
    return result


def estimate_tanzania():
    """Tanzania: WFP dataset, Admin-2 markets."""
    wfp_path = 'data/Prices-Export-Wed Apr 08 2026 17_24_52 GMT-0400 (Eastern Daylight Time).csv'

    if not os.path.exists(wfp_path):
        print("  WFP Tanzania data not found, skipping")
        return None

    print("Loading Tanzania WFP data...")
    df = pd.read_csv(wfp_path)
    maize = df[df['Commodity'] == 'Maize (white)'].copy()
    maize['date'] = pd.to_datetime(maize['Price Date'], format='%d/%m/%Y')
    maize['ym'] = maize['date'].dt.year * 100 + maize['date'].dt.month

    # Get Admin-2 centroids
    admin = gpd.read_file('data/processed/tanzania_calibrated.gpkg')

    district_coords = {}
    for dist in maize['Admin 2'].unique():
        match = admin[admin['NAME_2'].str.lower() == dist.lower()]
        if len(match) == 0:
            match = admin[admin['NAME_2'].str.contains(dist, case=False, na=False)]
        if len(match) > 0:
            district_coords[dist] = (match.iloc[0]['centroid_lon'], match.iloc[0]['centroid_lat'])

    maize = maize[maize['Admin 2'].isin(district_coords)]
    markets = list(district_coords.keys())
    n_mkts = len(markets)
    print(f"  {n_mkts} markets matched to Admin-2 centroids")

    pairs = list(combinations(range(n_mkts), 2))
    pair_dist = np.array([
        haversine(district_coords[markets[i]][1], district_coords[markets[i]][0],
                  district_coords[markets[j]][1], district_coords[markets[j]][0])
        for i, j in pairs
    ])
    valid = [(p, d) for p, d in zip(pairs, pair_dist) if d > 5.0]
    pairs = [v[0] for v in valid]
    pair_dist = np.array([v[1] for v in valid])

    pivot = maize.pivot_table(index='Admin 2', columns='ym', values='Price')
    pivot = pivot.reindex(markets)

    all_gaps, all_dists, all_ym = [], [], []
    for ym in pivot.columns:
        prices = pivot[ym].values
        ok = ~np.isnan(prices) & (prices > 0)
        if ok.sum() < 5:
            continue
        for idx, (i, j) in enumerate(pairs):
            if ok[i] and ok[j]:
                all_gaps.append(abs(np.log(prices[i]) - np.log(prices[j])))
                all_dists.append(pair_dist[idx])
                all_ym.append(ym)

    result = run_regression(np.array(all_gaps), np.array(all_dists),
                            np.array(all_ym), f"Tanzania (WFP, {n_mkts} markets, maize)")
    result['n_markets'] = n_mkts
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--country', default='all', choices=['kenya', 'tanzania', 'all'])
    args = parser.parse_args()

    os.makedirs('outputs', exist_ok=True)
    results = []

    print(f"\n{'='*60}")
    print("PRICE-DISTANCE ELASTICITY ESTIMATION")
    print(f"{'='*60}")

    if args.country in ('kenya', 'all'):
        r = estimate_kenya()
        if r:
            results.append(r)

    if args.country in ('tanzania', 'all'):
        r = estimate_tanzania()
        if r:
            results.append(r)

    # Summary
    if results:
        print(f"\n{'='*60}")
        print("SUMMARY")
        print(f"{'='*60}")
        for r in results:
            print(f"  {r['label']}")
            print(f"    δ = {r['beta_level']:.6f}/km, scale = {r['implied_scale']:.0f} km, "
                  f"N = {r['n_obs']:,}")

        # Save
        out_path = 'outputs/price_elasticity_results.txt'
        with open(out_path, 'w') as f:
            f.write("Price-Distance Elasticity Results\n")
            f.write("=" * 50 + "\n\n")
            for r in results:
                f.write(f"{r['label']}\n")
                f.write(f"  Markets: {r['n_markets']}, Obs: {r['n_obs']:,}\n")
                f.write(f"  Level: δ = {r['beta_level']:.8f}/km "
                        f"(SE {r['se_level']:.8f}, t={r['t_level']:.1f})\n")
                f.write(f"  Log-log: δ = {r['beta_log']:.6f} (SE {r['se_log']:.6f})\n")
                f.write(f"  Implied scale: {r['implied_scale']:.0f} km\n")
                f.write(f"  Mean price gap: {r['mean_gap']:.4f}\n\n")
        print(f"\n  Saved to {out_path}")


if __name__ == '__main__':
    main()
