"""
price_road_regression.py — Estimate distance elasticity using road network distances.

Regresses bilateral price gaps on road network distances (from Dijkstra's)
instead of straight-line distances. This gives a cleaner measure of trade
costs because it reflects actual routes, not as-the-crow-flies distance.

Usage:
    python3 src/price_road_regression.py --country KEN

Requires:
    - data/processed/{country}_market_road_distances.npy
    - data/processed/{country}_market_locations.csv
    - data/raw/rtfp_prices.csv
"""

import os
import argparse
import numpy as np
import pandas as pd


RTFP_PATH = 'data/raw/rtfp_prices.csv'


def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)
    a = np.sin(dlat/2)**2 + np.cos(np.radians(lat1))*np.cos(np.radians(lat2))*np.sin(dlon/2)**2
    return 2 * R * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def run_regression(gaps, dists, yms, label, origins=None):
    """Run price-distance regression with time FE (demeaned)."""
    reg = pd.DataFrame({'gap': gaps, 'dist': dists, 'ym': yms})

    # Add origin-time FE if provided
    if origins is not None:
        reg['origin'] = origins
        reg['origin_ym'] = reg['origin'].astype(str) + '_' + reg['ym'].astype(str)
        group_col = 'origin_ym'
    else:
        group_col = 'ym'

    # Demean
    for col in ['gap', 'dist']:
        reg[col + '_dm'] = reg[col] - reg.groupby(group_col)[col].transform('mean')

    X = reg['dist_dm'].values
    y = reg['gap_dm'].values

    beta = (X @ y) / (X @ X)
    resid = y - beta * X
    se = np.sqrt(np.sum(resid**2) / (len(resid) - 1) / np.sum(X**2))
    t = beta / se
    r2 = 1 - np.sum(resid**2) / np.sum(y**2) if np.sum(y**2) > 0 else 0

    med_dist = np.median(dists)
    implied_scale = 1 / beta if beta > 0 else float('inf')

    print(f"\n  {label}")
    print(f"  {'─' * 55}")
    print(f"  Obs: {len(gaps):,}, FE: {group_col}")
    print(f"  δ = {beta:.8f}/km (SE {se:.8f}, t = {t:.1f})")
    print(f"  R² = {r2:.4f}")
    print(f"  Mean |log(p_i/p_j)|: {gaps.mean():.4f} ({100*gaps.mean():.1f}%)")
    print(f"  Median distance: {med_dist:.0f} km")
    print(f"  Price gap at median: {100*beta*med_dist:.1f}%")
    print(f"  Implied scale: {implied_scale:.0f} km")

    return {
        'label': label, 'n_obs': len(gaps), 'beta': beta, 'se': se,
        't': t, 'r2': r2, 'median_dist': med_dist, 'implied_scale': implied_scale,
        'mean_gap': gaps.mean(),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--country', required=True, help='ISO3 code')
    parser.add_argument('--max-year', type=int, default=2019, help='Exclude post-COVID')
    args = parser.parse_args()

    iso3 = args.country.upper()

    # Map ISO3 to country name for file paths
    try:
        from country_config import get_config_by_iso3
        cfg = get_config_by_iso3(iso3)
        name_lower = cfg['country_name'].lower().replace(' ', '_').replace("'", "")
    except:
        name_lower = iso3.lower()

    print(f"\n{'=' * 60}")
    print(f"PRICE-DISTANCE REGRESSION: {iso3} (Road Network Distances)")
    print(f"{'=' * 60}")

    # Load road distances
    rd_path = f'data/processed/{name_lower}_market_road_distances.npy'
    mkt_path = f'data/processed/{name_lower}_market_locations.csv'

    if not os.path.exists(rd_path):
        print(f"ERROR: {rd_path} not found. Run market_road_distances.py first.")
        return

    road_dist = np.load(rd_path)
    mkts = pd.read_csv(mkt_path)
    n_mkts = len(mkts)
    mkt_names = mkts['mkt_name'].values
    print(f"  Markets: {n_mkts}, Road distance matrix: {road_dist.shape}")

    # Compute straight-line distances for comparison
    sl_dist = np.zeros((n_mkts, n_mkts))
    for i in range(n_mkts):
        for j in range(n_mkts):
            sl_dist[i, j] = haversine(mkts.iloc[i]['lat'], mkts.iloc[i]['lon'],
                                       mkts.iloc[j]['lat'], mkts.iloc[j]['lon'])

    # Load price data
    print(f"  Loading RTFP prices (up to {args.max_year})...")
    df = pd.read_csv(RTFP_PATH,
                     usecols=['ISO3', 'mkt_name', 'year', 'month',
                              'o_maize_fao', 'o_beans_fao',
                              'o_livestock_goat_s_fao', 'o_food_price_index'])
    prices = df[(df['ISO3'] == iso3) & (df['year'] <= args.max_year)].copy()
    prices['ym'] = prices['year'] * 100 + prices['month']
    prices = prices[prices['mkt_name'].isin(set(mkt_names))]
    print(f"  Price obs: {len(prices):,}")

    # Connected pairs mask
    connected = np.isfinite(road_dist) & (road_dist > 0) & ~np.eye(n_mkts, dtype=bool)

    # Run for each commodity × distance type
    commodities = {
        'o_maize_fao': 'Maize',
        'o_beans_fao': 'Beans',
        'o_livestock_goat_s_fao': 'Goat livestock',
        'o_food_price_index': 'Food price index',
    }

    all_results = []

    for col, comm_label in commodities.items():
        pivot = prices.pivot_table(index='mkt_name', columns='ym', values=col)
        pivot = pivot.reindex(mkt_names)

        for dist_type, dist_matrix, dist_label in [
            ('road', road_dist, 'Road network'),
            ('straight', sl_dist, 'Straight-line'),
        ]:
            all_gaps, all_dists, all_yms, all_origins = [], [], [], []

            for ym in pivot.columns:
                p = pivot[ym].values
                ok = ~np.isnan(p) & (p > 0)
                if ok.sum() < 10:
                    continue
                for i in range(n_mkts):
                    for j in range(i + 1, n_mkts):
                        if ok[i] and ok[j] and connected[i, j]:
                            gap = abs(np.log(p[i]) - np.log(p[j]))
                            d = dist_matrix[i, j]
                            if d > 0 and np.isfinite(d):
                                all_gaps.append(gap)
                                all_dists.append(d)
                                all_yms.append(ym)
                                all_origins.append(i)

            if not all_gaps:
                continue

            gaps = np.array(all_gaps)
            dists = np.array(all_dists)
            yms = np.array(all_yms)
            origins = np.array(all_origins)

            # Time FE only
            label = f"{comm_label} × {dist_label} (time FE)"
            r = run_regression(gaps, dists, yms, label)
            r['commodity'] = comm_label
            r['distance_type'] = dist_label
            r['fe'] = 'time'
            all_results.append(r)

            # Origin-time FE (only for road distance to keep output manageable)
            if dist_type == 'road':
                label = f"{comm_label} × {dist_label} (origin-time FE)"
                r = run_regression(gaps, dists, yms, label, origins=origins)
                r['commodity'] = comm_label
                r['distance_type'] = dist_label
                r['fe'] = 'origin-time'
                all_results.append(r)

    # Summary comparison
    print(f"\n{'=' * 60}")
    print(f"SUMMARY: Road vs Straight-Line Distance")
    print(f"{'=' * 60}")
    print(f"\n  {'Commodity':<20s} {'Distance':<15s} {'FE':<12s} {'δ/km':>12s} {'Scale':>8s} {'R²':>8s}")
    print(f"  {'-' * 77}")

    for r in all_results:
        print(f"  {r['commodity']:<20s} {r['distance_type']:<15s} {r['fe']:<12s} "
              f"{r['beta']:.6f}   {r['implied_scale']:>7.0f} {r['r2']:>8.4f}")

    # Road/straight-line ratio
    print(f"\n  Road distance / straight-line ratio:")
    finite = connected & (sl_dist > 0)
    ratios = road_dist[finite] / sl_dist[finite]
    print(f"    Mean: {ratios.mean():.2f}x, Median: {np.median(ratios):.2f}x")

    # Save
    out_path = f'outputs/price_road_regression_{iso3}.txt'
    os.makedirs('outputs', exist_ok=True)
    with open(out_path, 'w') as f:
        f.write(f"Price-Distance Regression: {iso3}\n")
        f.write(f"Road network distances from Dijkstra's algorithm\n")
        f.write("=" * 50 + "\n\n")
        for r in all_results:
            f.write(f"{r['label']}\n")
            f.write(f"  δ = {r['beta']:.8f}/km (t={r['t']:.1f}), R²={r['r2']:.4f}\n")
            f.write(f"  Scale = {r['implied_scale']:.0f} km, N = {r['n_obs']:,}\n\n")
    print(f"\n  Saved: {out_path}")


if __name__ == '__main__':
    main()
